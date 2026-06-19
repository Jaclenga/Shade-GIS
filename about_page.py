import streamlit as st


def render_about_page(study_summary: str, data_citation: str) -> None:
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
        - Community-submitted shade observations and votes

        ## References

        Hillsborough Area Regional Transit. *General Transit Feed Specification (GTFS) Data Feed* [Data set].
        Retrieved June 17, 2026.

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
