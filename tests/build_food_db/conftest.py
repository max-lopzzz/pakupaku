import os
import shutil

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


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
