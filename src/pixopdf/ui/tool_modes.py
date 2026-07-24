from dataclasses import dataclass
from enum import StrEnum


class WorkspaceMode(StrEnum):
    ORGANIZE = "organize"
    MERGE = "merge"
    SPLIT = "split"
    LAYOUT = "layout"
    CONVERT = "convert"
    PROTECT = "protect"
    SIGN = "sign"
    COMPRESS = "compress"


class ModeStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    COMING_SOON = "coming_soon"


@dataclass(frozen=True, slots=True)
class ModeSpec:
    mode: WorkspaceMode
    label: str
    icon_name: str
    home_title: str
    home_description: str
    workspace_title: str
    status: ModeStatus
    planned_actions: tuple[str, ...] = ()

    @property
    def status_label(self) -> str:
        return {
            ModeStatus.READY: "Disponible",
            ModeStatus.PARTIAL: "Fonctions essentielles",
            ModeStatus.COMING_SOON: "Bientôt",
        }[self.status]

    @property
    def is_selectable(self) -> bool:
        """Whether the mode currently exposes at least one usable workflow."""
        return self.status is not ModeStatus.COMING_SOON

    def icon_asset(self, theme_name: str) -> str:
        return f"pixopdf-vector-assets/icons/{theme_name}/{self.icon_name}.svg"


MODE_SPECS: dict[WorkspaceMode, ModeSpec] = {
    WorkspaceMode.ORGANIZE: ModeSpec(
        WorkspaceMode.ORGANIZE,
        "Organiser",
        "organize",
        "Organisez les pages de vos PDF",
        "Réordonnez, tournez, dupliquez ou retirez des pages sans modifier l’original.",
        "Toutes les pages",
        ModeStatus.READY,
    ),
    WorkspaceMode.MERGE: ModeSpec(
        WorkspaceMode.MERGE,
        "Fusionner",
        "merge",
        "Fusionnez plusieurs PDF",
        "Déposez plusieurs documents, ajustez leur ordre puis exportez un PDF unique.",
        "Pages à fusionner",
        ModeStatus.READY,
    ),
    WorkspaceMode.SPLIT: ModeSpec(
        WorkspaceMode.SPLIT,
        "Diviser",
        "split",
        "Divisez un PDF avec précision",
        "Créez un PDF par page, par lots ou à partir de plages personnalisées.",
        "Pages à diviser",
        ModeStatus.READY,
        ("Un PDF par page", "Lots de pages", "Plages personnalisées"),
    ),
    WorkspaceMode.LAYOUT: ModeSpec(
        WorkspaceMode.LAYOUT,
        "Mise en page",
        "layout",
        "Préparez la mise en page",
        "Ajoutez des pages blanches et préparez vos documents pour l’écran ou l’impression.",
        "Pages à mettre en page",
        ModeStatus.PARTIAL,
        ("Modifier le format", "Plusieurs pages par feuille"),
    ),
    WorkspaceMode.CONVERT: ModeSpec(
        WorkspaceMode.CONVERT,
        "Convertir",
        "convert",
        "Convertissez vos documents",
        "Transformez localement un PDF en images ou des images en PDF.",
        "Document à convertir",
        ModeStatus.COMING_SOON,
        ("PDF vers images", "Images vers PDF", "Extraire les images"),
    ),
    WorkspaceMode.PROTECT: ModeSpec(
        WorkspaceMode.PROTECT,
        "Protéger",
        "secure",
        "Protégez vos PDF",
        "Ajoutez un mot de passe et contrôlez les permissions sans envoyer vos fichiers.",
        "Document à protéger",
        ModeStatus.COMING_SOON,
        ("Mot de passe d’ouverture", "Permissions", "Retirer un mot de passe"),
    ),
    WorkspaceMode.SIGN: ModeSpec(
        WorkspaceMode.SIGN,
        "Signer",
        "sign",
        "Signez et validez vos PDF",
        "Préparez une signature visuelle ou une signature numérique vérifiable.",
        "Document à signer",
        ModeStatus.COMING_SOON,
        ("Signature visuelle", "Signature numérique", "Ajouter la date"),
    ),
    WorkspaceMode.COMPRESS: ModeSpec(
        WorkspaceMode.COMPRESS,
        "Compresser",
        "compress",
        "Réduisez la taille de vos PDF",
        "Choisissez un profil de compression adapté à l’envoi, au web ou à l’archivage.",
        "Document à compresser",
        ModeStatus.COMING_SOON,
        ("Compression légère", "Compression équilibrée", "Compression maximale"),
    ),
}


def coerce_mode(value: WorkspaceMode | str) -> WorkspaceMode:
    return value if isinstance(value, WorkspaceMode) else WorkspaceMode(value)
