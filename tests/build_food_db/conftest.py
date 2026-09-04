import csv
import os
import shutil

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def csv_to_xlsx(csv_path, xlsx_path, sheet=None, extra_rows=()):
    """Write a committed CSV fixture out as a one-sheet .xlsx workbook.

    The xlsx sources are fed real workbooks, but a CSV fixture stays readable
    and diffable in git — so the workbook is built at test setup time rather
    than committing a binary blob. ``extra_rows`` are appended after the CSV.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    if sheet is not None:
        ws.title = sheet
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            ws.append(row)
    for row in extra_rows:
        ws.append(list(row))
    wb.save(str(xlsx_path))
    return str(xlsx_path)


def cofid_raw_dir(tmp_path, csv_path=None, extra_rows=()):
    """Build the CoFID workbook the extractor expects (name + sheet taken
    from ``sources/cofid.py``) inside tmp_path/cofid/, and return that dir."""
    from scripts.build_food_db.sources import cofid

    d = tmp_path / "cofid"
    if not d.exists():
        d.mkdir(parents=True)
    csv_to_xlsx(csv_path or os.path.join(FIX, "cofid_slice.csv"),
                d / cofid.FILE, cofid.SHEET, extra_rows)
    return str(d)


def usda_raw_dir(tmp_path):
    """Copy the committed USDA *_slice.csv fixtures into tmp_path/usda/
    under the real FDC release filenames, and return that dir as a str."""
    d = tmp_path / "usda"
    d.mkdir()
    shutil.copy(os.path.join(FIX, "usda_food_slice.csv"), d / "food.csv")
    shutil.copy(os.path.join(FIX, "usda_food_nutrient_slice.csv"),
                d / "food_nutrient.csv")
    shutil.copy(os.path.join(FIX, "usda_nutrient_slice.csv"), d / "nutrient.csv")
    return str(d)


def cnf_raw_dir(tmp_path):
    """Copy the committed CNF *_slice.csv fixtures into tmp_path/cnf/ under
    the real multi-file relational release names, and return that dir."""
    d = tmp_path / "cnf"
    d.mkdir()
    shutil.copy(os.path.join(FIX, "cnf_food_name_slice.csv"), d / "FOOD NAME.csv")
    shutil.copy(os.path.join(FIX, "cnf_nutrient_name_slice.csv"),
                d / "NUTRIENT NAME.csv")
    shutil.copy(os.path.join(FIX, "cnf_nutrient_amount_slice.csv"),
                d / "NUTRIENT AMOUNT.csv")
    return str(d)


def afcd_raw_dir(tmp_path):
    """Copy the committed AFCD *_slice.xlsx fixtures into tmp_path/afcd/ under
    the real Release 2 workbook names, and return that dir."""
    d = tmp_path / "afcd"
    d.mkdir()
    shutil.copy(os.path.join(FIX, "afcd_food_details_slice.xlsx"),
                d / "Release2_Food_Details.xlsx")
    shutil.copy(os.path.join(FIX, "afcd_nutrients_slice.xlsx"),
                d / "Release2_Food_Nutrients_per_100g.xlsx")
    return str(d)


def single_file_raw_dir(tmp_path, source_id, fixture_name, real_name):
    """Copy one committed fixture slice into tmp_path/<source_id>/<real_name>
    and return that dir as a str. Used by the single-file extractors."""
    d = tmp_path / source_id
    d.mkdir()
    shutil.copy(os.path.join(FIX, fixture_name), d / real_name)
    return str(d)
