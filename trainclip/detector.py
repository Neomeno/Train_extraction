"""TorchVision detector adapter; separate from event planning and FFmpeg."""

from __future__ import annotations

from pathlib import Path

from .core import Sample


class TrainDetector:
    """Detect the COCO 'train' category with MobileNetV3 Faster R-CNN."""

    def __init__(self, model_name: str, device: str, min_area_percent: float):
        import torch
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_320_fpn,
        )

        self.torch = torch
        self.min_area_percent = min_area_percent
        weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.COCO_V1
        if model_name == "COCO_V1":
            # TorchVision downloads the official weights into its local cache once.
            model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)
        else:
            model_path = Path(model_name).expanduser()
            if not model_path.is_file():
                raise RuntimeError("モデルは COCO_V1 または互換 state_dict ファイルを指定してください")
            model = fasterrcnn_mobilenet_v3_large_320_fpn(
                weights=None, weights_backbone=None
            )
            state = torch.load(model_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
        categories = weights.meta["categories"]
        self.train_ids = {
            index for index, name in enumerate(categories) if name.casefold() == "train"
        }
        if not self.train_ids:
            raise RuntimeError("モデルのカテゴリに train がありません")
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("GPU が利用できません。CPU または自動を選択してください")
        self.device = torch.device(device)
        self.transforms = weights.transforms()
        self.model = model.to(self.device).eval()

    def detect(self, time: float, frame: object) -> Sample:
        # FFmpeg yields BGR; TorchVision expects RGB CHW in [0, 1].
        rgb = frame[:, :, ::-1].copy()
        tensor = self.torch.from_numpy(rgb).permute(2, 0, 1)
        image = self.transforms(tensor).to(self.device)
        with self.torch.inference_mode():
            result = self.model([image])[0]
        height, width = frame.shape[:2]
        best_confidence = 0.0
        best_area = 0.0
        for box, score, category in zip(
            result["boxes"], result["scores"], result["labels"]
        ):
            if int(category.item()) not in self.train_ids:
                continue
            confidence = float(score.item())
            if confidence < 0.1:
                continue
            x1, y1, x2, y2 = box.tolist()
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            area_percent = 100 * area / (width * height)
            if area_percent >= self.min_area_percent and confidence > best_confidence:
                best_confidence = confidence
                best_area = area_percent
        return Sample(time, best_confidence, best_area)

