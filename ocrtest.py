from doctr.models import ocr_predictor
from doctr.io import DocumentFile

model = ocr_predictor(pretrained=True)

doc = DocumentFile.from_images("2026-05-12_04.31.49.png")

result = model(doc)

result.show()

