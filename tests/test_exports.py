from __future__ import annotations

import io
import json

import pandas as pd

import builder_app
from builder_app import dataframe_to_geojson, deploy_readme, deploy_script, study_config_json
from platform_store import add_shade_label, create_project, list_shade_labels


def test_export_csv_geojson_raw_labels_and_config(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    add_shade_label(
        project_id,
        {
            "stop_id": "1001",
            "labeler_id": "alice",
            "labeler_role": "Expert",
            "shade_category": "No Shade",
            "confidence": 0.95,
            "source": "expert_review",
        },
        db_path,
    )
    builder_app.st.session_state.clear()
    builder_app.st.session_state["active_project_id"] = project_id
    builder_app.st.session_state["project"] = project
    builder_app.st.session_state["taxonomy"] = taxonomy
    builder_app.st.session_state["methodology"] = methodology
    builder_app.st.session_state["visualization"] = visualization
    builder_app.st.session_state["import_log"] = [{"source": "pytest", "format": "CSV", "rows": 2}]

    stops_csv = minimal_stops.to_csv(index=False)
    labels_csv = list_shade_labels(project_id, path=db_path).to_csv(index=False)
    geojson = json.loads(dataframe_to_geojson(minimal_stops))
    config = json.loads(study_config_json())

    assert len(pd.read_csv(io.StringIO(stops_csv))) == 2
    assert len(pd.read_csv(io.StringIO(labels_csv))) == 1
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    assert geojson["features"][0]["properties"]["stop_id"] == "1001"
    assert config["project"]["name"] == "Test Shade Study"
    assert config["taxonomy"][0]["name"] == taxonomy[0]["name"]
    assert config["import_log"][0]["rows"] == 2


def test_deploy_script_supports_existing_private_repositories():
    script = deploy_script("owner/private-shade-study")

    assert '[Alias("TargetRepo")]' in script
    assert '[Alias("Repo")]' not in script
    assert '[ValidateSet("create", "existing")]' in script
    assert '$Mode = "create"' in script
    assert "$AllowPublicTarget" in script
    assert 'function Invoke-Native' in script
    assert 'function Invoke-NativeOutput' in script
    assert "Could not access GitHub repository '$repoSlug'" in script
    assert 'Invoke-NativeOutput "gh" @("repo", "view", $repoSlug' in script
    assert '$env:TEMP' in script
    assert '[guid]::NewGuid()' in script
    assert 'Invoke-Native "gh" @("repo", "clone", $RepositoryName, $publishDir)' in script
    assert 'Invoke-Native "git" @("clone", $remoteUrl, $publishDir)' in script
    assert "Clone command completed but publish directory was not created" in script
    assert 'Copy-SafeBundleFiles -Destination $publishDir' in script
    assert 'README.md' in script
    assert '.env.*' in script
    assert 'Invoke-Native "git" @("status")' in script
    assert 'Invoke-Native "git" @("diff", "--stat")' in script
    assert 'Invoke-Native "git" @("diff", "--cached", "--stat")' in script
    assert 'Read-Host "$Message Type PUBLISH to continue"' in script
    assert 'Commit-And-Push -TargetBranch $Branch' in script
    assert 'Remove-Item -LiteralPath $publishDir -Recurse -Force' in script


def test_deploy_readme_documents_existing_private_repo_flow(project):
    readme = deploy_readme("owner/private-shade-study", project)

    assert "After Downloading The Zip" in readme
    assert "By default, your browser should save the bundle to your Downloads folder" in readme
    assert '$BundleName = "private-shade-study.zip"' in readme
    assert '$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName' in readme
    assert '$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "private-shade-study"' in readme
    assert "Expected the deploy bundle at $ZipPath" in readme
    assert "Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force" in readme
    assert "Set-Location $ExtractTo" in readme
    assert 'Test-Path ".\\deploy_to_github.ps1"' in readme
    assert "extracted deploy bundle folder" in readme
    assert "gh auth status" in readme
    assert 'gh repo view "owner/private-shade-study"' in readme
    assert "Could not resolve to a Repository" in readme
    assert '-Mode create -RepositoryName "owner/private-shade-study"' in readme
    assert '-Mode existing -RepositoryName "owner/private-shade-study" -Branch "main"' in readme
    assert "-Repo " not in readme
    assert "pre-existing private repository" in readme
    assert "_shade_gis_publish_*" in readme
    assert "git diff --stat" in readme
    assert "PUBLISH" in readme
    assert "-AllowPublicTarget" in readme
    assert ".env*" in readme


def test_deploy_readme_create_mode_does_not_verify_missing_repo(project):
    readme = deploy_readme("owner/new-shade-study", project, deploy_mode="create")

    assert 'gh repo view "owner/new-shade-study"' not in readme
    assert '-Mode create -RepositoryName "owner/new-shade-study"' in readme
    assert "create the target repository used for this bundle" in readme
