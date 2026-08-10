from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

import pikepdf

from pixopdf.pdf.exceptions import PdfError

from ._atomic import atomic_output_path, ensure_distinct_paths


class ProtectionError(PdfError):
    """Base error for password and permission operations."""


class ProtectionPasswordError(ProtectionError):
    """Raised when an encrypted input cannot be opened with the supplied password."""


class EncryptionStrength(StrEnum):
    AES_128 = "aes_128"
    AES_256 = "aes_256"

    @property
    def revision(self) -> Literal[4, 6]:
        return 4 if self is EncryptionStrength.AES_128 else 6


@dataclass(frozen=True, slots=True)
class ProtectionPermissions:
    """PDF permission flags.

    These flags are advisory: a PDF reader may choose not to enforce them.
    """

    accessibility: bool = True
    extract: bool = False
    modify_annotation: bool = False
    modify_assembly: bool = False
    modify_form: bool = False
    modify_other: bool = False
    print_lowres: bool = True
    print_highres: bool = False

    def as_pikepdf(self) -> pikepdf.Permissions:
        return pikepdf.Permissions(
            accessibility=self.accessibility,
            extract=self.extract,
            modify_annotation=self.modify_annotation,
            modify_assembly=self.modify_assembly,
            modify_form=self.modify_form,
            modify_other=self.modify_other,
            print_lowres=self.print_lowres,
            print_highres=self.print_highres,
        )


@dataclass(frozen=True, slots=True)
class ProtectionOptions:
    owner_password: str = field(repr=False)
    user_password: str = field(default="", repr=False)
    source_password: str = field(default="", repr=False)
    permissions: ProtectionPermissions = field(default_factory=ProtectionPermissions)
    strength: EncryptionStrength = EncryptionStrength.AES_256
    encrypt_metadata: bool = True

    def __post_init__(self) -> None:
        if not self.owner_password:
            raise ValueError("Un mot de passe propriétaire est requis")


@dataclass(frozen=True, slots=True)
class RemoveProtectionOptions:
    password: str = field(repr=False)


class ProtectionService:
    """Apply or remove standard PDF encryption without modifying the source."""

    def protect(
        self,
        source: Path,
        destination: Path,
        options: ProtectionOptions,
    ) -> Path:
        self._validate_paths(source, destination)
        encryption = pikepdf.Encryption(
            owner=options.owner_password,
            user=options.user_password,
            R=options.strength.revision,
            allow=options.permissions.as_pikepdf(),
            aes=True,
            metadata=options.encrypt_metadata,
        )
        try:
            with (
                pikepdf.open(source, password=options.source_password) as pdf,
                atomic_output_path(destination) as temporary,
            ):
                # PDF/A does not permit encryption, so protection explicitly
                # converts the output to an ordinary encrypted PDF.
                pdf.save(
                    temporary,
                    encryption=encryption,
                    preserve_pdfa=False,
                )
        except pikepdf.PasswordError as exc:
            raise ProtectionPasswordError(
                "Le mot de passe du document source est incorrect ou manquant"
            ) from exc
        except (pikepdf.PdfError, OSError) as exc:
            raise ProtectionError("Impossible de protéger le document PDF") from exc
        return destination

    def remove_protection(
        self,
        source: Path,
        destination: Path,
        options: RemoveProtectionOptions,
    ) -> Path:
        self._validate_paths(source, destination)
        try:
            with (
                pikepdf.open(source, password=options.password) as pdf,
                atomic_output_path(destination) as temporary,
            ):
                pdf.save(temporary, encryption=False)
        except pikepdf.PasswordError as exc:
            raise ProtectionPasswordError("Le mot de passe du document est incorrect") from exc
        except (pikepdf.PdfError, OSError) as exc:
            raise ProtectionError("Impossible de retirer la protection du document PDF") from exc
        return destination

    @staticmethod
    def _validate_paths(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise ProtectionError(f"Fichier PDF introuvable : {source.name}")
        ensure_distinct_paths(source, destination)
