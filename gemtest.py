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





# just a container class, we need this because
# i can't figure out how to get pydantic or
# the google genai api to just return a list
class ShopList(RootModel):
    root: list[Shop]




# this might not be necessary if we use
# another method but for now it's here to make sure
# we get the nested objects
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




# path definitions
images_path = "images"         # directory containing images to extract data from
results_path = "results.csv"   # result data
finished_path = "finished.txt" # file containing a list of images we've already looked at
                               # TODO: make this part of results.csv

finished = []                  # list of images we've already looked at




# if results exist, grab a list of what images
# we've already looked at
if isfile(finished_path):
    with open(finished_path, "r") as fp:
        finished = fp.read().splitlines()
else:
    with open(finished_path, "w") as fp:
        pass




# write csv header
fieldnames = list(Shop.model_json_schema()["properties"].keys())
if not isfile(results_path):
    with open(results_path, "w") as fp:
        writer = csv.DictWriter(fp, fieldnames = fieldnames)
        writer.writeheader()




# add all images from our images directory into a queue
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
                model='gemini-3.5-flash',
                contents=images+[
#                    minecraft_font,
                    '''
                    ocr the images

                    signs follow this format:
                    <shop owner>
                    <quantity>
                    B [buy price] : [sell price] S
                    <item id>

                    if the sign doesn't roughly follow this format, ignore it
                    if the sign is partially obscured, too small or too blurry, ignore it

                    c and o are similar, don't confuse them
                    5 and S are similar, don't confuse them
                    the B or S may be before or after the number, don't include the B or the S

                    the buy or sell price is optional, if one is not present, don't include it

                    also, include the XYZ coordinates from the top left of the screen in the output
                    '''
                ],
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=get_schema(ShopList),
                ),
            )

            # validate the response and convert it into an object
            shops = TypeAdapter(ShopList).validate_python(json.loads(response.text))

            # write actual result data
            with open(results_path, "a") as fp:
                for shop in shops.root:
                    writer = csv.DictWriter(fp, fieldnames = fieldnames)
                    writer.writerow(shop.model_dump())

            # then write down the names of the files we've just
            # processed so we don't have to look at them again
            with open(finished_path, "a") as fp:
                for image_path in image_paths_to_add:
                    fp.write(image_path + "\n")
        except ServerError as e:
            print(f"server error {e.code} {e.status} {e.message}, trying again")

        request_completed = True
        print(f"{total_images-q.qsize()}/{total_images} images processed")

print("done")

