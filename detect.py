import time
from pathlib import Path

import numpy as np
from numpy import random

import cv2
import torch

from torchvision.ops import box_convert

from utils.image_utils import plot_one_box, read_image
from hubconf import yolov5s


def load_names(category_path):
    names = []
    with open(category_path, 'r') as f:
        for line in f:
            names.append(line.strip())
    return names


@torch.no_grad()
def inference(model, img_name, device, is_half=False):
    model.eval()
    img = cv2.imread(img_name)
    img = read_image(img, is_half=is_half)
    img = img.to(device)
    t1 = time.time()
    detections = model([img])
    time_consume = time.time() - t1

    return detections, time_consume


@torch.no_grad()
def overlay_boxes(detections, path, time_consume, args):
    img = cv2.imread(path) if args.save_img else None

    for i, pred in enumerate(detections):  # detections per image
        det_logs = ''
        save_path = Path(args.output_dir).joinpath(Path(path).name)
        txt_path = Path(args.output_dir).joinpath(Path(path).stem)

        if pred is not None and len(pred) > 0:
            # Rescale boxes from img_size to im0 size
            boxes, scores, labels = pred['boxes'].round(), pred['scores'], pred['labels']

            # Print results
            for c in labels.unique():
                n = (labels == c).sum()  # detections per class
                det_logs += '%g %ss, ' % (n, args.names[int(c)])  # add to string

            # Write results
            for xyxy, conf, cls_name in zip(boxes, scores, labels):
                if args.save_txt:  # Write to file
                    # normalized cxcywh
                    cxcywh = box_convert(xyxy, in_fmt="xyxy", out_fmt="cxcywh").tolist()
                    with open(f'{txt_path}.txt', 'a') as f:
                        f.write(('%g ' * 5 + '\n') % (cls_name, *cxcywh))  # label format

                if args.save_img:  # Add bbox to image
                    label = '%s %.2f' % (args.names[int(cls_name)], conf)
                    plot_one_box(
                        xyxy,
                        img,
                        label=label,
                        color=args.colors[int(cls_name) % len(args.colors)],
                        line_thickness=3,
                    )

        # Print inference time
        print('%sDone. (%.3fs)' % (det_logs, time_consume))

        # Save results (image with detections)
        if args.save_img:
            cv2.imwrite(str(save_path), img)

    return (boxes.tolist(), scores.tolist(), labels.tolist())


def main(args):
    print(args)
    device = torch.device("cuda") if torch.cuda.is_available() and args.gpu else torch.device("cpu")

    model = yolov5s(
        pretrained=True,
        min_size=args.min_size,
        max_size=args.max_size,
        score_thresh=args.score_thresh,
        nms_thresh=args.nms_thresh,
    )
    model.eval()
    model = model.to(device)

    # Initialize

    # half = device.type != 'cpu'  # half precision only supported on CUDA
    is_half = False

    # Load model
    if is_half:
        model.half()  # to FP16

    # Get names and colors
    args.names = load_names(Path(args.labelmap))
    args.colors = [[random.randint(0, 255) for _ in range(3)] for _ in range(len(args.names))]

    # Run inference
    img = torch.zeros((3, 320, 320), device=device)  # init img
    if is_half:
        img = img.half()
    _ = model([img])  # run once

    t0 = time.time()
    model_out, time_consume = inference(model, args.input_source, device, is_half)
    total_time_consume = time.time() - t0

    # Process detections
    _ = overlay_boxes(model_out, args.input_source, time_consume, args)

    if args.save_txt or args.save_img:
        print(f'Results saved to {args.output_dir}')

    print('Total time: (%.3fs)' % (total_time_consume))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--labelmap', type=str, default='./notebooks/assets/coco.names',
                        help='path where the coco category in')
    parser.add_argument('--input_source', type=str, default='./test/assets/zidane.jpg',
                        help='path where the source images in')
    parser.add_argument('--output_dir', type=str, default='./data-bin/output',
                        help='path where to save')
    parser.add_argument('--min_size', type=int, default=640,
                        help='inference min size (pixels)')
    parser.add_argument('--max_size', type=int, default=640,
                        help='inference min size (pixels)')
    parser.add_argument('--score_thresh', type=float, default=0.15,
                        help='object confidence threshold')
    parser.add_argument('--nms_thresh', type=float, default=0.5,
                        help='IOU threshold for NMS')
    parser.add_argument('--gpu', action='store_true',
                        help='GPU switch')
    parser.add_argument('--save_txt', action='store_true',
                        help='save results to *.txt')
    parser.add_argument('--save_img', action='store_true',
                        help='save image inference results')
    parser.add_argument('--classes', nargs='+', type=int,
                        help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic_nms', action='store_true',
                        help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true',
                        help='augmented inference')

    args = parser.parse_args()

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    main(args)
