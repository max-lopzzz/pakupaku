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


def single_file_raw_dir(tmp_path, source_id, fixture_name, real_name):
    """Copy one committed fixture slice into tmp_path/<source_id>/<real_name>
    and return that dir as a str. Used by the single-file extractors."""
    d = tmp_path / source_id
    d.mkdir()
    shutil.copy(os.path.join(FIX, fixture_name), d / real_name)
    return str(d)
