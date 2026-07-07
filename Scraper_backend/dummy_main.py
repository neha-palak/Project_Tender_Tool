from Scraper_backend.datasetManager import json_to_excel

json_to_excel(
    json_filename="uk_file.json",
    excel_filename="uk_live_tenders_pipeline.xlsx"
)

print("Excel generated")