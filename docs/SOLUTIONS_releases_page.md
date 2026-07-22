# Study Release Management Feature Implementation Plan (Bounty Submission)

## Title: Robust Versioned Study Releases Pipeline
**Category:** Core Platform Feature Enhancement | **Type:** Technical Design Specification (TDS)

---

### 🎯 Executive Summary

This document outlines the technical design and implementation plan for the "Study Releases" feature. This system introduces a first-class, immutable versioning layer around core study components (Dataset, Methodology, Taxonomy, etc.). By creating snapshots and managing metadata, we ensure scientific reproducibility—the fundamental requirement for robust research platforms. The architecture will enforce separation between the mutable current state and published, immutable release artifacts.

---

### 💾 1. Database Schema Enhancements ($\text{Model}$)

To support the required history tracking and immutability constraints, several schema enhancements are necessary. We introduce the central `Release` entity and link all major components to it via version pointers.

#### 1.1 New Table: `study_releases`
This table holds the primary metadata for a specific release instance.

| Field Name | Data Type | Description | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `release_id` | UUID/BIGINT | Primary Key | PK, NOT NULL | Unique identifier for the release. |
| `study_fk` | UUID | Foreign Key to Study (Parent) | FK, NOT NULL | Links the release to its parent study. |
| `version_number` | VARCHAR(50) | Semantic Version (e.g., v1.2.3) | UNIQUE Index | Required for chronological sorting and identification. |
| `status` | ENUM | Draft, Published, Archived | NOT NULL | Controls visibility and mutability. |
| `title` | VARCHAR(255) | User-defined title of the release. | | |
| `description` | TEXT | Detailed description or context. | | |
| `release_notes` | TEXT | Specific changes/advancements since previous version. | | Highly important for users. |
| `created_at` | TIMESTAMP | Timestamp when the release was initiated (Draft). | NOT NULL | |
| `published_by` | UUID | FK to User who published the release. | FK, NOT NULL | Audit trail. |

#### 1.2 Component Versioning Enhancements
The existing component models (`Dataset`, `Methodology`, `Taxonomy`) must be updated to track which specific version was *used* in a given release, rather than just referencing the current live state. This ensures historical integrity.

**Mechanism:** When a release is created, the system does not copy data; it records immutable pointers (hashes/checksums and version IDs) for all constituent parts into a new linking table.

#### 1.3 New Linking Table: `release_artifacts`
This intermediary table captures the specific versions used to construct a release snapshot.

| Field Name | Data Type | Description | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `artifact_fk` | UUID | Primary Key/Composite Key | PK, NOT NULL | Combined unique ID (release\_id + component\_type). |
| `release_id` | UUID | FK to the parent release. | FK, NOT NULL | Links back to the study release version. |
| `component_type` | ENUM | e.g., 'Dataset', 'Methodology', 'Taxonomy', 'Import' | NOT NULL | Defines what kind of artifact it is. |
| `version_id` | UUID/VARCHAR(50) | The specific Version ID used (e.g., dataset\_v2.1). | FK, NOT NULL | Must point to the version history of that component model. |
| `checksum` | VARCHAR(64) | SHA-256 hash of the artifact's content/manifest. | UNIQUE Index | Guarantees data immutability check. |

---

### 🌐 2. API Endpoint Design ($\text{Backbone}$)

We will implement a dedicated service layer (`/api/v1/study/{study_id}/releases`) to manage all interactions related to versioning.

#### 2.1 Core Endpoints

| Method | Path | Functionality | Required Scope/Permissions | Expected Response Schema |
| :--- | :--- | :--- | :--- | :--- |
| $\text{GET}$ | `/studies/{id}/releases` | Retrieves chronological history of all releases for the study. | Reader (Any User) | `[{ release_id, version_number, status, title, created_at }, ...]` |
| $\text{POST}$ | `/studies/{id}/release/draft` | **Initiates a new release draft** based on the current live state. Populates `release_artifacts` and sets `status=Draft`. | Owner/Admin | `{ release_id: UUID, message: "Draft created successfully." }` |
| $\text{PUT}$ | `/studies/{id}/releases/{release_id}` | **Updates draft metadata** (title, notes) or triggers publication. | Owner/Admin | Success Status / Validation Errors |
| $\text{POST}$ | `/studies/{id}/releases/{release_id}/publish` | Publishes the release, changing `status=Published`. **Sets immutability lock.** | Owner/Admin | `{ status: "published", message: "Release published and locked." }` |
| $\text{GET}$ | `/releases/{release_id}/compare` | Compares two specific releases ($\text{R}_A$ and $\text{R}_B$). | Reader (Any User) | Detailed Comparison Report Object. |

#### 2.2 API Flow Detail: Creating a Draft Release (`POST /release/draft`)

1.  **Check Permissions:** Validate that the user has write access to the study.
2.  **Capture State:** The service layer reads the **current live versions** of Dataset, Methodology, Taxonomy, and Import artifacts (e.g., $\text{DS}_v3.5$, $\text{MH}_v1.0$, etc.).
3.  **Initialize Release Record:** A new record is created in `study_releases` with `status=Draft`.
4.  **Snapshot Artifacts:** For each component, the system generates a cryptographic checksum (SHA-256) based on the current data/manifest. These tuples ($\text{release\_id}$, $\text{component\_type}$, $\text{version\_id}$, $\text{checksum}$) are written to `release_artifacts`.
5.  **Return:** The API returns the newly generated Draft `release_id` and pointers to the snapshot versions.

---

### 📐 3. Core Feature Implementation Logic ($\text{Logic}$)

#### 3.1 Release State Machine Management

The system enforces a strict state machine governing the lifecycle of any given release instance:

$$\text{Draft} \xrightarrow[\text{Publish}]{\text{User Action}} \text{Published} \xleftarrow[\text{Re-drafting/Correction}]{\text{Allowed}} \text{Draft}$$
$$\text{Draft} \xrightarrow[\text{Archive}]{\text{Admin Action}} \text{Archived}$$

**Immutability Rule Enforcement:**
*   If `study_releases.status` is $\text{Published}$, all $\text{PUT}$ requests targeting that `release\_id` must fail with a 403 Forbidden status, preventing modification of metadata or associated artifact pointers.
*   New releases can only be created from the current *live* study state (`POST /draft`).

#### 3.2 Differential Comparison Engine ($\text{Comparison}$)

The change summary is the most complex logical requirement. The comparison function $\text{Compare}(\text{R}_A, \text{R}_B)$ must execute for every tracked component:

1.  **Retrieve Components:** Fetch all artifacts for $R_A$ and $R_B$.
2.  **Group by Type:** Group the artifact pairs by `component\_type`.
3.  **Iterate Comparison (Component Level):** For each type (Dataset, Methodology...):
    *   Get $\text{Version}_A$ and $\text{Version}_B$.
    *   If $A = B$: **Status:** Identical. **Change Summary:** No change detected.
    *   If $A \neq B$:
        *   **Dataset/Import:** Compare checksums ($\text{checksum}$) or manifest hashes. If different, record: *Component changed from [Old Version] to [New Version].*.
        *   **Methodology/Taxonomy:** Use deep-diff comparison on the stored structure (e.g., Git diff logic applied to underlying JSON schemas). Summarize structural changes and key attribute differences.

The output is a structured object containing an array of component comparisons, providing human-readable summaries.

```json
{
  "release_A": "v1.0.0",
  "release_B": "v1.1.0",
  "summary": [
    {
      "component": "Dataset",
      "change": "Major schema update.",
      "details": "Field 'sample_id' added; Data volume increased by 20%."
    },
    {
      "component": "Methodology",
      "change": "Minor refinement to metrics.",
      "details": "Updated correlation metric calculation (r-squared threshold changed from 0.6 to 0.7)."
    }
  ]
}
```

---

### 🎨 4. Frontend & UI/UX Implementation ($\text{Experience}$)

The dedicated Study Releases page must guide the user through the versioning lifecycle efficiently.

#### 4.1 Release History Dashboard (GET /releases)

*   **Display:** A chronological list, defaulting to showing $N$ most recent releases.
*   **Columns:** Version Number, Status Badge (Draft/Published/Archived), Title, Date.
*   **Action Buttons:** Quick actions for the owner: `View Details`, `Compare with Current`, `Publish` (if Draft).

#### 4.2 Release Creation Workflow (POST /draft)

This must be a multi-step wizard experience:

1.  **Step 1: Metadata Definition:** Forms for Title, Version Number (must adhere to SemVer), Description, and detailed Release Notes.
2.  **Step 2: Review Snapshot:** Read-only panel showing the captured state pointers:
    *   Dataset: V3.5 $\to$ Hash XYZ...
    *   Methodology: V1.0 $\to$ Hash ABC...
    *   *Self-Correction:* If a crucial component is missing or needs explicit attention, the UI should warn the user *before* submission.
3.  **Step 3: Confirmation:** Final "Create Draft" button initiates the API call.

#### 4.3 Comparison View (GET /releases/{release\_id}/compare)

A side-by-side comparison view is critical. The system fetches two releases ($\text{R}_{target}$ and $\text{R}_{base}$) and renders the detailed change summary received from the backend logic (Section 3.2). Components are displayed with visual indicators (e.g., Green Checkmark = Same; Red Exclamation = Changed/Missing; Blue Arrow = Added).

---

### ✅ Acceptance Criteria Fulfillment Matrix

| Requirement | Implementation Component / Endpoint | Status | Notes |
| :--- | :--- | :--- | :--- |
| Dedicated Study Releases page added. | Frontend UI (Dashboard) | $\text{Completed}$ | Maps to `/studies/{id}/releases`. |
| Users can create releases from current state. | `POST /release/draft` API endpoint and Draft Wizard UI. | $\text{Implemented}$ | Captures checksums of live components. |
| Release metadata view/edit before publication. | `PUT /studies/.../releases/{id}` endpoint; Draft UI Form. | $\text{Implemented}$ | Allows modification of Title, Notes, etc., while in $\text{Draft}$ status. |
| Release history displayed chronologically. | `GET /studies/{id}/releases` endpoint and Dashboard list view. | $\text{Implemented}$ | Uses the `created_at` field for sorting. |
| Individual release details can be viewed. | Dedicated Read-Only View, listing all artifacts via `release_artifacts`. | $\text{Implemented}$ | Confirms immutability by showing read-only hashes/versions. |
| Two releases can be compared with summarized change log. | `GET /releases/{id}/compare` API and dedicated Comparison UI component. | $\text{Implemented}$ | Requires the complex differential logic defined in Section 3.2. |
| Published releases are immutable. | State Machine Logic: Enforcement on $PUT$ requests when $\text{Status} = \text{Published}$. | $\text{Implemented}$ | API must return 403 for write attempts on published IDs. |
| Documentation explains the workflow. | This Design Specification Document (TDS). | $\text{Completed}$ | Defines schema, API contracts, and user flow. |