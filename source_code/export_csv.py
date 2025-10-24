from source_code.api_client import SimapAPIClient, build_search_filters
import os


def main():
    # Filter bequem per Helper und ENV-Variablen setzen
    types_env = os.getenv("SIMAP_TYPES", "OB00,OB01,OB02,OB03,OB04,OB05,OB06,OB07,OB08,OB09")
    filters = build_search_filters(
        start_date=os.getenv("SIMAP_START", "2024-01-01"),
        end_date=os.getenv("SIMAP_END", "2024-06-30"),
        types=[s.strip() for s in types_env.split(",") if s.strip()],
        contract_types=[s.strip() for s in os.getenv("SIMAP_CONTRACT_TYPES", "").split(",") if s.strip()],
        procedures=[s.strip() for s in os.getenv("SIMAP_PROCEDURES", "").split(",") if s.strip()],
        cpv=[s.strip() for s in os.getenv("SIMAP_CPV", "").split(",") if s.strip()],
        bkp=[s.strip() for s in os.getenv("SIMAP_BKP", "").split(",") if s.strip()],
        keywords=os.getenv("SIMAP_KEYWORDS"),
    )
    client = SimapAPIClient()
    # Möglichst wenige Seiten: bis zu 1000 Einträge pro Seite
    pubs = client.iterate_publications(filters, records_per_page=1000)
    out_name = os.getenv("SIMAP_CSV_NAME", "auftraege_2024-01-01_2024-06-30_all.csv")
    client.export_publications_csv(pubs, filename=out_name)


if __name__ == "__main__":
    main()
