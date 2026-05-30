from google import genai
from google.genai import types
from google.genai.errors import ServerError
from os import listdir
from os.path import join, isfile
from pydantic import BaseModel, RootModel, Field, TypeAdapter
from typing import Optional, List
import json
import queue
import csv

class Shop(BaseModel):
    shop_owner: str = Field(description="Minecraft username of the Shop Owner")
    quantity: int = Field(description="Quantity per transaction")
    buy_price: Optional[str] = Field(description="Cost to buy")
    sell_price: Optional[str] = Field(description="Cost to sell")
    item_id: str = Field(description="Item name")
    x: int
    y: int
    z: int

class ShopList(RootModel):
    root: list[Shop]

def get_schema(cls: BaseModel):
    """
    Converts a Pydantic model to a JSON schema dictionary.
    """
    schema = cls.model_json_schema()
    if "$defs" not in schema:
        return schema

    defs = schema.pop("$defs")

    def _resolve(schema):
        if "$ref" in schema:
            ref = schema.pop("$ref")
            schema.update(defs[ref.split("/")[-1]])
        if "properties" in schema:
            for prop in schema["properties"].values():
                _resolve(prop)
        if "items" in schema:
            _resolve(schema["items"])
        schema.pop("title",None)

    _resolve(schema)
    return schema

images_path = "images"
results_path = "results.csv"
finished_path = "finished.txt"
finished = []

if isfile(finished_path):
    with open(finished_path, "r") as fp:
        finished = fp.read().splitlines()
else:
    with open(finished_path, "w") as fp:
        pass

fieldnames = list(Shop.model_json_schema()["properties"].keys())

if not isfile(results_path):
    with open(results_path, "w") as fp:
        writer = csv.DictWriter(fp, fieldnames = fieldnames)
        writer.writeheader()

q = queue.Queue()

for path in listdir(images_path):
    if path not in finished:
        q.put(path)

print('connecting to gemini api')
client = genai.Client()

#minecraft_font = client.files.upload(file="font.png")

total_images = q.qsize()

print(f"processing {total_images} images")

while not q.empty():
    images = []
    image_paths_to_add = []
    for i in range(10):
        try:
            path = q.get_nowait()
            image_paths_to_add.append(path)
            with open(join('images', path), 'rb') as f:
                images.append(
                    types.Part.from_bytes(
                        data=f.read(),
                        mime_type='image/png',
                    )
                )
#                print(f'opened {path}')
        except queue.Empty:
            break
        except Error:
            print(f'failed to open image {path}')

    request_completed = False
    while not request_completed:
        try:
            response = client.models.generate_content(
#               model='gemini-3.5-flash',
                model='gemini-3.1-flash-lite',
                contents=images+[
#                    minecraft_font,
                    '''
                    ocr the images

                    signs follow this format:
                    <shop owner>
                    <quantity>
                    B [buy price] : S [sell price]
                    <item id>

                    if the sign doesn't roughly follow this format, ignore it
                    if the sign is partially obscured, too small or too blurry, ignore it

                    the B or S may be before or after the number, don't include the B or the S
                    c and o are similar, don't confuse them

                    the buy or sell price is optional, if one is not present, don't include it

                    also, include the XYZ coordinates from the top left of the screen in the output
                    '''
                ],
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=get_schema(ShopList),  # Use the get_schema function here
                ),
            )

            shops = TypeAdapter(ShopList).validate_python(json.loads(response.text))
            with open(results_path, "a") as fp:
                for shop in shops.root:
                    writer = csv.DictWriter(fp, fieldnames = fieldnames)
                    writer.writerow(shop.model_dump())
            with open(finished_path, "a") as fp:
                for image_path in image_paths_to_add:
                    fp.write(image_path + "\n")
        except ServerError as e:
            print(f"server error {e.code} {e.status} {e.message}, trying again")
        request_completed = True
        print(f"{total_images-q.qsize()}/{total_images} images processed")
print("done")

