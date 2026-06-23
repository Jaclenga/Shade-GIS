import streamlit as st


def render_about_page(
    study_summary: str,
    data_citation: str,
    heat_vulnerability_citation: str,
    heat_vulnerability_metadata_citation: str,
) -> None:
    st.title("Tampa Shade Study")
    st.markdown(f"### {study_summary}")
    st.markdown(
        """
        ## About the Study

        Tampa's hot and humid climate can make waiting for transit uncomfortable, particularly at bus stops with
        limited protection from direct sunlight. Inspired by research from Austin, Texas, examining the relationship
        between bus stop shade, extreme heat, and transit use, this project explores how shade is distributed across
        Tampa's bus network and provides a platform for community-driven data collection.

        The Tampa Shade Study combines official bus stop locations from HART's GTFS feed with community-submitted
        shade observations to create an open map of shade conditions throughout the city. The goal is to support
        transportation planning, accessibility research, climate resilience initiatives, and public understanding of
        the rider experience.

        By identifying which stops provide meaningful shade and which do not, the project helps highlight
        opportunities for tree planting, shelter installation, and other improvements that can make transit more
        comfortable and accessible for riders.

        Classifications were based on visible shade coverage of the waiting area in available imagery rather than
        the mere presence of nearby vegetation or structures. This is especially important with Street View winter
        imagery: code what visibly shades the waiting area, not what might shade it at another time.

        Waiting area: The space where a passenger would reasonably stand or sit while waiting for transit, including
        benches when present.

        Research on thermal comfort at bus stops has shown that the waiting environment plays an important role in
        how riders perceive public transportation. In subtropical climates, exposure to direct sunlight, limited
        shade, and high temperatures can reduce comfort and satisfaction while waiting for a bus. Together with
        evidence that tree canopy and shade infrastructure may help mitigate the impacts of extreme heat on transit
        users, these findings suggest that the quality of the waiting environment is an important component of an
        accessible, resilient, and rider-friendly transit system. The Tampa Shade Study seeks to make these conditions
        more visible by documenting shade availability across the region's bus network and providing data that can
        inform future improvements.

        ## Data Sources

        - Hillsborough Area Regional Transit (HART) General Transit Feed Specification (GTFS) Data Feed
        - Hillsborough County Heat Vulnerability Index ArcGIS Feature Layer
        - Community-submitted shade observations and votes

        ## Dataset Fields Used In The App

        - `shade_coverage`: the observed or voted amount of shade reaching the waiting area, using No Shade,
          Limited, or Significant.
        - `shade_sources`: the observed or voted source labels for shade reaching the waiting area. This can hold
          multiple labels, such as Natural; Constructed; Manmade, when more than one source visibly shades riders.
        - `shading`: the derived map label used to keep the original color legend and summary tables compatible
          with the source and coverage fields.
        - `heat_vulnerability_index`: the county's weighted heat-vulnerability score for the surrounding block
          group. Higher values indicate greater relative vulnerability.
        - `heat_vulnerability_label`: the category label paired with the weighted HVI score, such as Least, Low,
          Moderate, Elevated, or Most Vulnerable.
        - `tree_canopy_pct`: the estimated share of surrounding tree canopy. Higher values suggest more nearby
          canopy and potentially more natural cooling in the area.
        - `lst_median`: the median land surface temperature for the surrounding block group. Higher values suggest
          hotter nearby surfaces and stronger local heat exposure.

        ## Shade Voting Guide

        ### Shade Source

        | Shade Source | Operational Definition |
        | --- | --- |
        | Natural | Trees, palms, hedges, or other vegetation visibly shade the waiting area |
        | Constructed | A designated, purpose-built bus shelter, awning, canopy, overhang, or similar passenger shelter visibly shades the waiting area |
        | Manmade | A nearby building, wall, or other non-shelter built feature visibly shades the waiting area |
        | Natural; Constructed; Manmade | More than one source type visibly shades the waiting area |

        ### Shade Coverage

        | Shade Coverage | Operational Definition |
        | --- | --- |
        | No Shade | No shade visibly reaches the waiting area |
        | Limited | Shade visibly reaches part of the waiting area, but does not cover most of it |
        | Significant | Shade visibly covers most of the waiting area or seating area |

        Trees, utility poles, signs, and nearby buildings are not classified as Constructed unless they are clearly
        intended to provide passenger shade or weather protection. Nearby buildings that visibly shade the waiting
        area should be coded as Manmade.

        ### Current App Labels

        | Category | Operational Definition |
        | --- | --- |
        | No Shade | No visible shelter and no vegetation visibly shading the waiting area |
        | Limited Natural Shade | Vegetation visibly shades part of the waiting area, but does not visibly cover most of it |
        | Significant Natural Shade | Vegetation visibly covers most of the waiting area or seating area |
        | Constructed Shade | A purpose-built shelter, awning, canopy, or overhang visibly shades the waiting area |
        | Manmade Shade | A nearby building or other non-shelter built feature visibly shades the waiting area |

        ## Classification Examples

        | Visible condition | Shade Source | Shade Coverage |
        | --- | --- | --- |
        | Bus shelter and trees both visibly shade the waiting area | Natural; Constructed | Limited or Significant, depending on coverage |
        | Purpose-built bus shelter visibly shades where riders would wait | Constructed | Limited or Significant, depending on coverage |
        | Large building casts shade onto the stop but is not intended as passenger shelter | Manmade | Limited or Significant, depending on coverage |
        | Only a small sign or pole shadow reaches the stop | None | None unless it visibly shades the waiting area |
        | Trees are nearby but do not visibly shade the waiting area | None | None |
        | Hedges or shrubs visibly shade the bench or waiting area | Natural | Limited or Significant, depending on coverage |
        | Palms provide partial coverage | Natural | Limited |
        | Large oak canopy covers the stop | Natural | Significant |

        ## References

        Hillsborough Area Regional Transit. *General Transit Feed Specification (GTFS) Data Feed* [Data set].
        Retrieved June 17, 2026.

        Hillsborough County. (n.d.). *Heat Vulnerability Index* [Feature layer]. ArcGIS Feature Server.
        Retrieved June 20, 2026, from
        https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer

        Hillsborough County. (n.d.). *Heat Vulnerability Index (FeatureServer)* [Layer metadata].
        ArcGIS REST Services Directory. Retrieved June 20, 2026, from
        https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer/0

        Lanza, K., & Durand, C. P. (2021). *Heat-Moderating Effects of Bus Stop Shelters and Tree Shade on Public
        Transport Ridership*. International Journal of Environmental Research and Public Health, 18(2), 463.
        [https://doi.org/10.3390/ijerph18020463](https://doi.org/10.3390/ijerph18020463)

        Briant, S., Cushing, D. F., Washington, T., Pham, K., Pemasiri Hewa Thondilege, A. S., White, K. M., ... &
        Fookes, C. (2026). *Thermal Comfort at Bus Stops in a Subtropical Context: Investigating Perceptions and
        Satisfaction Levels While Waiting for the Bus*. In *Human-Building Interaction: The Nexus of Architecture,
        Building Science and Interaction Design* (pp. 119-145). Cham: Springer Nature Switzerland.
        """
    )
    st.caption(data_citation)
    st.caption(heat_vulnerability_citation)
    st.caption(heat_vulnerability_metadata_citation)
