"""
Implements a ReplayStrategy mixin for getting segmenting images via SAM model.

Uses SAM model:https://github.com/facebookresearch/segment-anything 

Usage:

    class MyReplayStrategy(SAMReplayStrategyMixin):
        ...
"""
from pprint import pformat
from mss import mss
import numpy as np
from openadapt import models
from segment_anything import SamPredictor, sam_model_registry, SamAutomaticMaskGenerator
from PIL import Image
from loguru import logger
from openadapt.events import get_events
from openadapt.utils import display_event, rows2dicts
from openadapt.models import Recording, Screenshot, WindowEvent
from pathlib import Path
import urllib
import numpy as np
import matplotlib.pyplot as plt

from openadapt.strategies.base import BaseReplayStrategy

CHECKPOINT_URL_BASE = "https://dl.fbaipublicfiles.com/segment_anything/"
CHECKPOINT_URL_BY_NAME = {
    "default": f"{CHECKPOINT_URL_BASE}sam_vit_h_4b8939.pth",
    "vit_l": f"{CHECKPOINT_URL_BASE}sam_vit_l_0b3195.pth",
    "vit_b": f"{CHECKPOINT_URL_BASE}sam_vit_b_01ec64.pth",
}
MODEL_NAME = "default"
CHECKPOINT_DIR_PATH = "./checkpoints"


class SAMReplayStrategyMixin(BaseReplayStrategy):
    def __init__(
        self,
        recording: Recording,
        model_name=MODEL_NAME,
        checkpoint_dir_path=CHECKPOINT_DIR_PATH,
    ):
        super().__init__(recording)
        self.sam_model = self._initialize_model(model_name, checkpoint_dir_path)
        self.sam_predictor = SamPredictor(self.sam_model)
        self.sam_mask_generator = SamAutomaticMaskGenerator(self.sam_model)

    def _initialize_model(self, model_name, checkpoint_dir_path):
        checkpoint_url = CHECKPOINT_URL_BY_NAME[model_name]
        checkpoint_file_name = checkpoint_url.split("/")[-1]
        checkpoint_file_path = Path(checkpoint_dir_path, checkpoint_file_name)
        if not Path.exists(checkpoint_file_path):
            Path(checkpoint_dir_path).mkdir(parents=True, exist_ok=True)
            logger.info(f"downloading {checkpoint_url=} to {checkpoint_file_path=}")
            urllib.request.urlretrieve(checkpoint_url, checkpoint_file_path)
        return sam_model_registry[model_name](checkpoint=checkpoint_file_path)

    def get_screenshot_bbox(self, screenshot: Screenshot) -> str:
        """
        Get the bounding boxes of objects in a screenshot image in XYWH format.

        Args:
            screenshot (Screenshot): The screenshot object containing the image.

        Returns:
            str: A string representation of a list containing the bounding boxes of objects.

        """
        image_resized = resize_image(screenshot.image)
        array_resized = np.array(image_resized)
        masks = self.sam_mask_generator.generate(array_resized)
        bbox_list = []
        for mask in masks:
            bbox_list.append(mask["bbox"])
            show_mask(mask["segmentation"], plt.gca())
            show_box(mask["bbox"], plt.gca())
        # for testing purposes
        # plt.figure(figsize=(10,10))
        # plt.imshow(array_resized)
        # plt.axis('on')
        # plt.show()
        return str(bbox_list)

    def get_click_event_bbox(self, screenshot: Screenshot) -> str:
        """
        Get the bounding box of the clicked object in a screenshot image in XYWH format.

        Args:
            screenshot (Screenshot): The screenshot object containing the image.

        Returns:
            str: A string representation of a list containing the bounding box of the clicked object.
            None: If the screenshot does not represent a click event with the mouse pressed.

        """
        logger.info(f"{len(screenshot.action_event)=}")
        for action_event in screenshot.action_event:
            if action_event.name in "click" and action_event.mouse_pressed == True:
                logger.info(f"{action_event=}")
                image_resized = resize_image(screenshot.image)
                array_resized = np.array(image_resized)

                # Resize mouse coordinates
                resized_mouse_x = int(action_event.mouse_x * 0.1)
                resized_mouse_y = int(action_event.mouse_y * 0.1)
                self.sam_predictor.set_image(array_resized)
                input_point = np.array([[resized_mouse_x, resized_mouse_y]])
                input_label = np.array([1])
                masks, scores, logits = self.sam_predictor.predict(
                    point_coords=input_point,
                    point_labels=input_label,
                    multimask_output=True,
                )
                best_mask_index = np.argmax(scores)
                best_mask = masks[best_mask_index]
                rows, cols = np.where(best_mask)
                # Calculate bounding box coordinates
                x0 = np.min(cols)
                y0 = np.min(rows)
                w = np.max(cols)
                h = np.max(rows)
                input_box = [x0, y0, w, h]
                plt.figure(figsize=(10, 10))
                plt.imshow(array_resized)
                show_mask(best_mask, plt.gca())
                show_box(input_box, plt.gca())
                show_points(input_point, input_label, plt.gca())
                plt.axis("on")
                plt.show()
                return [x0, y0, w - x0, h - y0]
        return []


def resize_image(image: Image) -> Image:
    """
    Resize the given image.

    Args:
        image (PIL.Image.Image): The image to be resized.

    Returns:
        PIL.Image.Image: The resized image.

    """
    resize_ratio = 0.1
    new_size = [int(dim * resize_ratio) for dim in image.size]
    image_resized = image.resize(new_size)
    return image_resized


def show_mask(mask, ax, random_color=False):
    if random_color:
        color = np.concatenate([np.random.random(3), np.array([0.6])], axis=0)
    else:
        color = np.array([30 / 255, 144 / 255, 255 / 255, 0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    ax.imshow(mask_image)


def show_points(coords, labels, ax, marker_size=375):
    pos_points = coords[labels == 1]
    neg_points = coords[labels == 0]
    ax.scatter(
        pos_points[:, 0],
        pos_points[:, 1],
        color="green",
        marker="*",
        s=marker_size,
        edgecolor="white",
        linewidth=1.25,
    )
    ax.scatter(
        neg_points[:, 0],
        neg_points[:, 1],
        color="red",
        marker="*",
        s=marker_size,
        edgecolor="white",
        linewidth=1.25,
    )


def show_box(box, ax):
    x0, y0 = box[0], box[1]
    w, h = box[2], box[3]
    ax.add_patch(
        plt.Rectangle((x0, y0), w, h, edgecolor="green", facecolor=(0, 0, 0, 0), lw=2)
    )