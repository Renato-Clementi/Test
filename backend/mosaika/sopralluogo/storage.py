"""Backend dei file. Il default è il disco; S3 si accende con le variabili d'ambiente."""

from __future__ import annotations

import shutil
from pathlib import Path

from mosaika.config import Settings


class Storage:
    def put_file(self, key: str, src: Path, content_type: str) -> None:
        raise NotImplementedError

    def open_path(self, key: str) -> Path:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


def _chiave_sicura(key: str) -> str:
    pulita = (key or "").replace("\\", "/").lstrip("/")
    parti = [parte for parte in pulita.split("/") if parte not in ("", ".")]
    if not parti or any(parte == ".." for parte in parti):
        raise ValueError("Chiave di storage non valida.")
    return "/".join(parti)


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        relativa = _chiave_sicura(key)
        dest = (self.root / relativa).resolve()
        if not str(dest).startswith(str(self.root)):
            raise ValueError("Chiave di storage non valida.")
        return dest

    def put_file(self, key: str, src: Path, content_type: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    def open_path(self, key: str) -> Path:
        dest = self._path(key)
        if not dest.is_file():
            raise FileNotFoundError(key)
        return dest

    def delete(self, key: str) -> None:
        dest = self._path(key)
        if dest.is_file():
            dest.unlink()


class S3Storage(Storage):
    """File finiti su un bucket compatibile S3. I pezzi parziali restano in locale."""

    def __init__(self, settings: Settings):
        import boto3

        self.bucket = settings.s3_bucket
        self.prefix = (settings.s3_prefix or "").strip("/")
        self.cache = settings.storage_dir().resolve() / "s3-cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region or "eu-south-1",
        )

    def _key(self, key: str) -> str:
        relativa = _chiave_sicura(key)
        if self.prefix:
            return f"{self.prefix}/{relativa}"
        return relativa

    def put_file(self, key: str, src: Path, content_type: str) -> None:
        self.client.upload_file(
            str(src),
            self.bucket,
            self._key(key),
            ExtraArgs={"ContentType": content_type or "application/octet-stream"},
        )

    def open_path(self, key: str) -> Path:
        dest = self.cache / _chiave_sicura(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, self._key(key), str(dest))
        return dest

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


def build_storage(settings: Settings) -> Storage:
    backend = (settings.storage_backend or "local").strip().lower()
    if backend == "local":
        return LocalStorage(settings.storage_dir())
    if backend == "s3":
        mancanti = [
            nome
            for nome, valore in (
                ("MOSAIKA_S3_BUCKET", settings.s3_bucket),
                ("MOSAIKA_S3_ACCESS_KEY", settings.s3_access_key),
                ("MOSAIKA_S3_SECRET_KEY", settings.s3_secret_key),
            )
            if not (valore or "").strip()
        ]
        if mancanti:
            raise RuntimeError(
                "Storage S3: mancano " + ", ".join(mancanti) + "."
            )
        return S3Storage(settings)
    raise RuntimeError(f"Storage sconosciuto: {backend}. Usa local oppure s3.")
