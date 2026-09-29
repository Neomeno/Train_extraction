# TrainClip 0.1

ローカルの MP4 を一定間隔で解析し、列車が映る区間を別の MP4 として保存する Windows 向けデスクトップアプリです。元動画は読み取り専用で扱い、移動・削除しません。

## 準備

1. Windows に Python 3.10 以降を入れ、`py` コマンドを有効にします。
2. [FFmpeg 公式ダウンロードページ](https://ffmpeg.org/download.html)から FFmpeg を導入し、`ffmpeg` と `ffprobe` を PATH から使えるようにします。
3. このフォルダで PowerShell を開き、`powershell -ExecutionPolicy Bypass -File .\install.ps1` を実行します。AI 関連パッケージは容量が大きいため、初回は時間がかかります。
4. `run.bat` を開きます。

初期モデルは TorchVision の `fasterrcnn_mobilenet_v3_large_320_fpn` の `COCO_V1` 重みです。初回使用時に重みが取得されるため、その時だけインターネット接続が必要です。その後は取得済みの重みでローカル解析できます。事前に用意した互換 `state_dict` ファイルを指定する場合は、「モデル」欄にそのパスを入力してください。モデルの出力カテゴリは COCO の定義と同じである必要があります。

GPU を指定して使用できない場合は、CPU または自動を選んでください。GPU 用 PyTorch の導入については [PyTorch 公式案内](https://pytorch.org/get-started/locally/) を参照してください。

## 使い方

1. 入力フォルダと出力フォルダを指定します。
2. 検出前後の秒数、最低動画時間、解析 fps、信頼度、最低連続検出数、イベント統合間隔を設定します。
3. 「解析開始」を押します。ファイル一覧、現在の進捗、全体の進捗が表示されます。
4. 列車を検出したファイルは、入力側の相対フォルダ構成を保ち、`元ファイル名_001.mp4` の形式で出力します。

同じ動画で検出前後の秒数・信頼度・イベント統合間隔を変えて再実行すると、保存済みのフレーム解析結果を再利用します。モデル、解析 fps、最低検出面積、入力ファイルが変わった場合は再解析します。「保存済み解析結果を使わず再解析」でも強制的に解析できます。中断後の再実行はファイル単位で再開できます。

出力先には `.trainclip.sqlite` と日付別の `logs/*.jsonl` も作成します。ログには動画情報、モデル、信頼度、検出区間、出力区間、処理時間、エラーを記録します。元動画は変更しません。

## 精度と制約

- 初期モデルは汎用の COCO 学習済み物体検出モデルです。COCO には `train` クラスがありますが、遠景や夜間、新幹線などの撮影条件での検出精度は保証できません。最初は短い素材で結果を確認し、信頼度や解析 fps を調整してください。
- 解析は指定 fps の時刻格子でサンプリングします。短時間だけ映る列車はサンプル間に入り、見逃す可能性があります。
- 「正確」は再エンコードします。「高速」はコピーするため、キーフレームの位置により開始位置がずれる場合があります。
- 同名の出力ファイルは再実行時に置き換えます。今回の実行で作られなかった過去の切り出しファイルは自動削除しません。
- Version 0.1 の範囲はフォルダ解析と自動切り出しです。タイムライン、動画プレビュー、手動編集、サムネイル、ROI は後続版の機能です。

## 構成

- `trainclip/detector.py`: TorchVision による列車判定
- `trainclip/core.py`: 連続検出、イベント統合、切り出し範囲計算
- `trainclip/video.py`: 動画情報取得、フレーム抽出、FFmpeg 出力
- `trainclip/cache.py`: SQLite による解析結果保存
- `trainclip/worker.py`: ファイルごとの処理・ログ・進捗
- `trainclip/app.py`: PySide6 画面

処理の独立性を保つため、検出器を変更する場合は `TrainDetector.detect()` が `Sample(time, confidence, area_percent)` を返す形に合わせます。

## 検証

純粋な判定ロジックとキャッシュのテストは `python -m unittest discover -s tests -v` で実行できます。実動画の検出品質と UI 操作は、対象 PC に Python・依存パッケージ・FFmpeg・サンプル MP4 を用意したうえで確認してください。

モデル API の参照: [TorchVision のモデル仕様](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.fasterrcnn_mobilenet_v3_large_320_fpn.html)。TorchVision の学習済み重みは別途取得され、このソース配布物には含めていません。重みの利用条件は [TorchVision の案内](https://github.com/pytorch/vision#pre-trained-model-license)を確認してください。

リポジトリの MIT ライセンスはこのアプリのソースコードに適用されます。PyTorch、TorchVision、および別途取得される学習済み重みの利用条件はそれぞれの提供元に従います。

