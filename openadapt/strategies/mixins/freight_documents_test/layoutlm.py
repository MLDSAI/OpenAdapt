from PIL import Image

import pytesseract
import numpy as np
import ipdb


# will convert to ReplayStrategy after get_layout is completed.
def get_layout(image: str):

        from transformers import LayoutLMv2Processor, LayoutLMv2ForTokenClassification
        import tensorflow as tf

        image = Image.open("rate_confirmation.png").convert("RGB")

        processor = LayoutLMv2Processor.from_pretrained(
                "microsoft/layoutlmv2-base-uncased")

        encoding = processor(image,truncation=True,return_offsets_mapping=True,return_tensors="pt")
        # we have to truncate the data otherwise classification doesnt worm
        offsets = encoding.pop('offset_mapping')
        token_classifier = LayoutLMv2ForTokenClassification.from_pretrained('microsoft/layoutlmv2-base-uncased')
        # iffy on the model tbh

        ocr_output = processor.tokenizer.decode(encoding['input_ids'][0])
        print(ocr_output)

        bounding_boxes_normalized = encoding.bbox.squeeze().tolist()
        width, height = image.size

        # offset map, subword
        subword = np.array(offsets.squeeze().tolist())[:,0] != 0
        true_boxes = [unnormalize_box(box, width, height) for idx, box in enumerate(bounding_boxes_normalized) if not subword[idx]]
        print(true_boxes)
        

        classification_output = token_classifier(**encoding)

        prediction_indices = classification_output.logits.argmax(-1).squeeze().tolist()
        print(prediction_indices)

        
def unnormalize_box(bbox, width, height):
     return [
         width * (bbox[0] / 1000),
         height * (bbox[1] / 1000),
         width * (bbox[2] / 1000),
         height * (bbox[3] / 1000),
     ]
        # LayoutLMV2 model has no heads on top, just a bare model. 

if __name__ == "__main__":
        get_layout("test.png")