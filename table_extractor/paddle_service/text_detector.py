from pathlib import Path
from typing import List

import numpy

from paddleocr.tools.infer.predict_det import TextDetector, logger

from table_extractor.model.table import BorderBox, TextField
from utility import create_predictor
from dataclasses import dataclass


@dataclass
class TextDetectorConfig:
    use_gpu = False
    ir_optim = True
    use_tensorrt = False
    gpu_mem = 8000

    det_algorithm = 'DB'
    det_limit_side_len = 960
    det_limit_type = 'max'

    det_db_thresh = 0.3
    det_db_box_thresh = 0.5
    det_db_unclip_ratio = 1.6

    det_east_score_thresh = 0.8
    det_east_cover_thresh = 0.1
    det_east_nms_thresh = 0.2

    det_sast_score_thresh = 0.5
    det_sast_nms_thresh = 0.2
    det_sast_polygon = False

    rec_algorithm = 'CRNN'
    rec_image_shape = "3, 32, 320"
    rec_char_type = 'ch'
    rec_batch_num = 6
    max_text_length = 25
    drop_score = 0.5

    use_angle_cls = False
    cls_image_shape = "3, 48, 192"
    label_list = ['0', '180']
    cls_batch_num = 30
    cls_thresh = 0.9

    enable_mkldnn = False
    use_zero_copy_run = False

    use_pdserving = False


def get_text_detector(
        det_model_dir='./paddle_detector/inference/ch_ppocr_mobile_v2.0_det_infer',
        cls_model_dir='./paddle_detector/inference/ch_ppocr_mobile_v2.0_cls_infer',
):
    args = TextDetectorConfig()
    args.det_model_dir = det_model_dir
    args.cls_model_dir = cls_model_dir
    args.use_angle_cls = True
    args.use_gpu = False
    text_detector = TextDetector(args)

    # Patch detector to prevent memory leak
    predictor, input_tensor, output_tensors = create_predictor(args, 'det', logger)
    text_detector.predictor = predictor
    text_detector.input_tensor = input_tensor
    text_detector.output_tensors = output_tensors
    return text_detector


def paddle_result_to_bboxes(dt_boxes, max_value=10 ** 7):
    bboxes = []
    for dt in dt_boxes:
        x1, y1 = max_value, max_value
        x2, y2 = -1, -1
        for pt in dt:
            x1 = int(min((x1, pt[0])))
            x2 = int(max((x2, pt[0])))
            y1 = int(min((y1, pt[1])))
            y2 = int(max((y2, pt[1])))
        bboxes.append((x1, y1, x2, y2))
    return bboxes


class PaddleDetector:
    def __init__(self, det_model_dir: Path, cls_model_dir: Path):
        self.text_detector = get_text_detector(
            str(det_model_dir.absolute()),
            str(cls_model_dir.absolute())
        )

    def extract_table_text(self, img: numpy.ndarray, border_box: BorderBox) -> List[TextField]:
        x1, y1, x2, y2 = border_box.box
        dt_boxes, elapse = self.text_detector(img[y1:y2, x1:x2])
        bboxes = paddle_result_to_bboxes(dt_boxes)
        return [TextField(bbox=cell, text='') for cell in
                (BorderBox(b[0]+x1, b[1]+y1, b[2]+x1, b[3]+y1) for b in bboxes)]


class PaddleSwitchWrapper(PaddleDetector):
    def __init__(self, det_model_dir: Path, cls_model_dir: Path, paddle_on):
        self.paddle_on = paddle_on
        if paddle_on:
            super(PaddleSwitchWrapper, self).__init__(det_model_dir, cls_model_dir)

    def extract_table_text(self, img: numpy.ndarray, border_box: BorderBox) -> List[TextField]:
        if not self.paddle_on:
            return []
        return super(PaddleSwitchWrapper, self).extract_table_text(img, border_box)
