import os
from types import NoneType
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import requests
from dotenv import load_dotenv
from PIL import Image
from PIL import ImageDraw
from tenacity import retry
from tenacity import stop_after_attempt
from tqdm import tqdm

load_dotenv()


JOBS = 46939,
RESULT_PATH = (Path(__file__).resolve().parent / "result").resolve()
USERNAME = os.getenv("USER-NAME")
PASSWORD = os.getenv("PASS-WORD")
API_URL = os.getenv("API_URL")

session = requests.Session()
session.auth = (USERNAME, PASSWORD)


@retry(stop=stop_after_attempt(10))
def get_data(job):
    archive = session.get(
        f"{API_URL}/jobs/{job}/data?type=chunk&number=0",
    ).content
    annotations = session.get(
        f"{API_URL}/jobs/{job}/annotations?action=download&format=CVAT%20for%20images%201.1",
    ).content
    if not archive or not annotations:
        raise Exception
    return archive, annotations


def download_zip(job, archive, is_image: bool = False):
    path = (RESULT_PATH / str(job)).resolve()
    if not path.exists():
        os.makedirs(path)
    path_zip = (path / f"{job}.zip").resolve()
    with open(path_zip, "wb") as f:
        f.write(archive)
    with ZipFile(path_zip, "r") as f:
        f.extractall(path)
        if is_image:
            images = f.filelist
            for image in images:
                image_name = image.filename.split(".")[0]
                format = image.filename.split(".")[1]
                os.rename(
                    path / image.filename,
                    path / f"{str(int(image_name))}.{format}",
                )
    if path_zip.exists():
        os.remove(path_zip)
    return path


def hex_to_rgb(hex_color):
    only_numbers = hex_color.lstrip("#")
    rgb_color_code = tuple(int(only_numbers[i : i + 2], 16) for i in (0, 2, 4))
    return rgb_color_code


def get_coords(polygon):
    coords = []
    row_coords = polygon.attrib.get("points").split(";")
    for coord in row_coords:
        x = float(coord.split(",")[0])
        y = float(coord.split(",")[1])
        coords.append((x, y))
    return coords


def get_colors(labels):
    colors = {}
    for label in labels:
        name = label.find("./name").text
        color = label.find("./color").text
        colors[name] = color
    return colors


def drow_masks(images):
    for image in images:
        image_id = image.attrib.get("id")
        image_path = (
            RESULT_PATH / str(job) / f"{image_id}.jpeg"
        )  # fixme: the format pointed directly

        image_origin = Image.open(image_path).convert("RGBA")
        mask = Image.new(mode="RGBA", size=image_origin.size)
        draw = ImageDraw.Draw(mask)

        polygons = image.findall("./polygon")

        for polygon in polygons:
            coords = get_coords(polygon)

            label = polygon.attrib.get("label")
            hex_color = colors[label]
            rgb_color = hex_to_rgb(hex_color)

            draw.polygon(coords, fill=rgb_color)

        image_res_file = image_path.parent / f"{image_id}.png"
        res_image = Image.alpha_composite(image_origin, mask)
        res_image.save(image_res_file)
        if image_path.exists():
            try:
                os.remove(image_path)
            except:
                print(f"deleting was failed: {image_id}")
        # fixme: back origin file names

def filter_images(images):
    image_list = []
    for image in images:
        polygon = image.find("./polygon")
        if not isinstance(polygon, NoneType):
            image_list.append(image)
    return image_list


# fixme: process incorrect login and password
if __name__ == "__main__":
    if not RESULT_PATH.exists():
        RESULT_PATH.mkdir()

    for job in tqdm(JOBS):
        images_zip, annotations_zip = get_data(job)
        image_path = download_zip(job, images_zip, is_image=True)
        annotations_path = download_zip(job, annotations_zip)

        file_xml = annotations_path / "annotations.xml"

        tree = ET.parse(file_xml)
        root = tree.getroot()

        labels = root.findall("./meta/job/labels//label")
        colors = get_colors(labels)

        images = root.findall(".//image")
        images_filtered = filter_images(images)
        
        drow_masks(images_filtered)

        if file_xml.exists():
            os.remove(file_xml)
