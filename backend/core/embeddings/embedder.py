from typing import List
import numpy as np
import os

# 设置显存优化环境变量（优先解决碎片问题）
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

try:
    import torch
    _TORCH_IMPORT_ERROR = None
except Exception as exc:
    torch = None
    _TORCH_IMPORT_ERROR = exc

SentenceTransformer = None
_SENTENCE_TRANSFORMERS_IMPORT_ERROR = None

# 本地模型目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
LOCAL_BGE_M3_PATH = os.environ.get("BGE_MODEL_PATH") or os.path.join(
    BASE_DIR, "huggingface", "hub", "models--BAAI--bge-m3",
    "snapshots", "5617a9f61b028005a4858fdac845db406aefb181",
)

_MODEL = None


def _import_sentence_transformers():
    global SentenceTransformer, _SENTENCE_TRANSFORMERS_IMPORT_ERROR

    if SentenceTransformer is not None:
        return

    try:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer
    except Exception as exc:
        _SENTENCE_TRANSFORMERS_IMPORT_ERROR = exc
        raise RuntimeError(f"sentence-transformers is not available; embeddings are unavailable ({exc})") from exc

    SentenceTransformer = _SentenceTransformer


def _ensure_embedding_runtime_available():
    if torch is None:
        detail = f" ({_TORCH_IMPORT_ERROR})" if _TORCH_IMPORT_ERROR else ""
        raise RuntimeError(f"PyTorch is not installed; embeddings are unavailable{detail}")

    _import_sentence_transformers()


def _get_device():
    if torch is not None and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_sentence_transformer(model_path: str, device: str):
    # Load weights on CPU first. Some torch/transformers/sentence-transformers
    # combinations can leave CUDA-loaded modules on the meta device and then
    # fail with "Cannot copy out of meta tensor; no data!" during .to(device).
    model = SentenceTransformer(model_path, device="cpu")

    if device == "cuda":
        try:
            model = model.to(device)
        except NotImplementedError as exc:
            if "meta tensor" not in str(exc).lower():
                raise
            print("Embedding model CUDA move failed because of meta tensor state; using CPU instead")
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower():
                raise
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("Embedding model CUDA move failed because GPU memory is insufficient; using CPU instead")

    return model


def _get_model(model_path: str = LOCAL_BGE_M3_PATH):
    global _MODEL
    if _MODEL is None:
        _ensure_embedding_runtime_available()
        _MODEL = _load_sentence_transformer(model_path, _get_device())
    return _MODEL


def embed_texts(texts: List[str], model_path: str = LOCAL_BGE_M3_PATH, batch_size: int = 8):
    """
    函数式接口：给 build_kb.py 用
    优化点：
    1. 默认本地加载 bge-m3
    2. 降低默认 batch_size 适配 6GB 显存
    3. 分批处理避免单次加载过多文本
    4. 增加显存清理和 OOM 自动降级 CPU
    """
    model = _get_model(model_path)
    all_vecs = []

    if not texts:
        return np.asarray([], dtype=np.float32)

    # 清空显存缓存
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        try:
            vecs = model.encode(
                batch_texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True
            )
            all_vecs.extend(vecs)

            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()

        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                print(f"⚠️ GPU显存不足，批次{i // batch_size + 1}自动降级到CPU处理")

                # 清理 GPU 缓存
                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()

                original_device = model._target_device
                model._target_device = torch.device("cpu")

                vecs = model.encode(
                    batch_texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    device="cpu"
                )
                all_vecs.extend(vecs)

                # 恢复原设备
                model._target_device = original_device
            else:
                raise e

    return np.asarray(all_vecs, dtype=np.float32)


class Embedder:
    """
    类接口：给 rag_singleton.py / pipeline.py 用
    同步优化：
    1. 默认本地加载 bge-m3
    2. 降低默认 batch_size
    3. 增加显存清理
    4. OOM 自动降级 CPU
    """

    def __init__(self, model_path: str = LOCAL_BGE_M3_PATH, device: str = None):
        _ensure_embedding_runtime_available()
        self.model_path = model_path
        self.device = device or _get_device()
        self.model = _load_sentence_transformer(model_path, self.device)

    def embed(self, texts: List[str], batch_size: int = 8) -> np.ndarray:
        all_vecs = []

        if not texts:
            return np.asarray([], dtype=np.float32)

        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            try:
                vecs = self.model.encode(
                    batch_texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True
                )
                all_vecs.extend(vecs)

                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"⚠️ GPU显存不足，批次{i // batch_size + 1}自动降级到CPU处理")

                    if torch is not None and torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    original_device = self.model._target_device
                    self.model._target_device = torch.device("cpu")

                    vecs = self.model.encode(
                        batch_texts,
                        batch_size=batch_size,
                        show_progress_bar=False,
                        normalize_embeddings=True,
                        device="cpu"
                    )
                    all_vecs.extend(vecs)

                    self.model._target_device = original_device
                else:
                    raise e

        return np.asarray(all_vecs, dtype=np.float32)
