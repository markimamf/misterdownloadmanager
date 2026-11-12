#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AMF_Rebrand.py - AMF Tools
Transforma um clone do Mister Download Manager (MDM, GPL-3.0-or-later, de Ahmed Nefzaoui)
no fork "AMF Download Manager".

Uso (na raiz do clone do SEU fork):
    python AMF_Rebrand.py                       # detecta usuario/repositorio pelo "git remote origin"
    python AMF_Rebrand.py --repo usuario/repo   # informa na mao
    python AMF_Rebrand.py --icon logo_amf.png   # tambem troca o icone (PNG quadrado, 512px ou mais; precisa do Pillow)
    python AMF_Rebrand.py --dry-run             # so mostra o que mudaria

O que muda:
  - Nome visivel: "Mister Download Manager" -> "AMF Download Manager"; sigla "MDM" -> "AMF"
    (janelas, menus, instalador, extensao, as 86 traducoes).
  - Executaveis: misterdownloadmanager*.exe -> amfdownloadmanager*.exe; pasta de dados, mutex e
    nome dos arquivos de release tambem (o AMF nao mistura dados com um MDM instalado).
  - Instalador: novo AppId (nao atualiza nem remove um MDM instalado), editor "AMF Informatica".
  - Atualizacoes, "Codigo-fonte" e relatorios de erro: apontam para o SEU fork, nao para o original.
  - GPL: aviso de versao modificada na janela Sobre, AMF-NOTICE.md e no README.

O que fica de proposito:
  - O id da ponte com o navegador (com.misterdownloadmanager.host) e os ids da extensao: assim a
    extensao oficial das lojas (Chrome/Firefox) funciona com o AMF Download Manager.
    Consequencia: nao use a integracao com navegador do MDM original e do AMF na mesma maquina.
  - O site de ajuda (misterdownloadmanager.com) e o link de apoio ao autor original.
  - Nomes internos dos crates (mdm-*), docs/, website/, CHANGELOG.md.

Roda uma vez por clone (grava .amf-rebrand). Para refazer: "git checkout . && git clean -fd" e rode de novo.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NEW_NAME = "AMF Download Manager"
NEW_SHORT = "AMF"
NEW_PASCAL = "AMFDownloadManager"
NEW_LOWER = "amfdownloadmanager"
PUBLISHER = "AMF Informatica"  # ASCII: o mdm.iss nao tem BOM
NEW_APP_ID = "5C1E7A94-2B6D-4F3A-9E48-0D7B63A1F2C5"

OLD_NAME = "Mister" + " Download Manager"
OLD_PASCAL = "Mister" + "DownloadManager"
OLD_LOWER = "mister" + "downloadmanager"
OLD_REPO = "anefzaoui/" + OLD_LOWER
OLD_APP_ID = "667DB4D8-32C2-4487-A0E5-5825BF29778C"
MARKER = ".amf-rebrand"

BINARY_EXT = {
    ".png", ".ico", ".icns", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".xz", ".gz", ".zip", ".bin",
    ".ttf", ".otf", ".woff", ".woff2", ".wav", ".ogg", ".mp3", ".mp4", ".torrent", ".pdb", ".exe",
    ".dll", ".pdf", ".7z", ".rar", ".ts", ".m4s",
}

# Trechos com o nome antigo em minusculas que NAO podem mudar (ids e enderecos de terceiros).
PROTECTED = [
    OLD_LOWER + ".com",                       # site de ajuda e id da extensao do Firefox
    "com." + OLD_LOWER + ".host",             # ponte com o navegador (native messaging)
    "io.github.anefzaoui." + OLD_LOWER,       # ids do macOS / Linux
]

# Sigla: nao mexe quando faz parte de nome de arquivo, id, URL ou chave ("MDM-test", "MDM.dmg", "dn=MDM%20").
SHORT_RE = re.compile(r"(?<![\w\-/.:=@%])MDM(?![\w\-/=@%]|[.:]\w)")
KEEP_SHORT = re.compile(r"Support &?MDM")  # o apoio vai para o autor original: continua dizendo MDM


class Stats:
    def __init__(self):
        self.files = 0
        self.changes = 0


def read_text(path: Path):
    raw = path.read_bytes()
    if b"\x00" in raw[:8192]:
        return None, None
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"  # 1 byte = 1 caractere: volta igual


def write_text(path: Path, text: str, enc: str):
    path.write_bytes(text.encode(enc))


def names(text: str, repo: str) -> str:
    """Repositorio, nome visivel, PascalCase e minusculas (com os trechos protegidos)."""
    owner, name = repo.split("/", 1)
    text = text.replace(OLD_REPO, repo)
    text = text.replace("|anefzaoui|" + OLD_LOWER + "|", f"|{owner}|{name}|")  # AppImage zsync
    text = text.replace(OLD_NAME, NEW_NAME)
    text = text.replace(OLD_PASCAL, NEW_PASCAL)
    for i, p in enumerate(PROTECTED):
        text = text.replace(p, f"\x00P{i}\x00")
    text = text.replace(OLD_LOWER, NEW_LOWER)
    for i, p in enumerate(PROTECTED):
        text = text.replace(f"\x00P{i}\x00", p)
    return text


def short(text: str) -> str:
    """Sigla MDM -> AMF, linha a linha, pulando as linhas do link de apoio."""
    out = []
    for line in text.splitlines(keepends=True):
        out.append(line if KEEP_SHORT.search(line) else SHORT_RE.sub(NEW_SHORT, line))
    return "".join(out)


def process(path: Path, repo: str, do_short: bool, stats: Stats, dry: bool):
    if path.suffix.lower() in BINARY_EXT or not path.is_file():
        return
    text, enc = read_text(path)
    if text is None:
        return
    new = names(text, repo)
    if do_short:
        new = short(new)
    if new != text:
        stats.files += 1
        if not dry:
            write_text(path, new, enc)


def walk(root: Path, base: str):
    d = root / base
    if d.is_file():
        yield d
    elif d.is_dir():
        for p in sorted(d.rglob("*")):
            if p.is_file() and "node_modules" not in p.parts and "target" not in p.parts:
                yield p


def extension_locales(root: Path, repo: str, stats: Stats, dry: bool):
    """extension/_locales/*/messages.json: nomes + sigla, menos as mensagens de apoio ao autor."""
    loc = root / "extension" / "_locales"
    en = loc / "en" / "messages.json"
    keep = set()
    if en.is_file():
        data = json.loads(en.read_text(encoding="utf-8"))
        keep = {k for k, v in data.items() if KEEP_SHORT.search(v.get("message", ""))}
    for f in sorted(loc.glob("*/messages.json")):
        text, enc = read_text(f)
        lines = text.splitlines(keepends=True)
        out, key = [], None
        for line in lines:
            m = re.match(r'\s{0,4}"([^"]+)":\s*\{', line)
            if m:
                key = m.group(1)
            line2 = names(line, repo)
            if key not in keep:
                line2 = SHORT_RE.sub(NEW_SHORT, line2)
            out.append(line2)
        new = "".join(out)
        if new != text:
            json.loads(new)  # continua JSON valido
            stats.files += 1
            if not dry:
                write_text(f, new, enc)


def edit(path: Path, old: str, new: str, dry: bool, regex: bool = False):
    """Troca pontual obrigatoria: avisa alto se o trecho nao existir (o upstream mudou)."""
    text, enc = read_text(path)
    if regex:
        new_text, n = re.subn(old, new, text, count=1, flags=re.S)
    else:
        n = text.count(old)
        new_text = text.replace(old, new, 1)
    if n == 0:
        raise SystemExit(f"ERRO: nao achei o trecho esperado em {path}:\n    {old[:90]}\n"
                         "O codigo original mudou nesse ponto; ajuste o AMF_Rebrand.py.")
    if not dry:
        write_text(path, new_text, enc)


ABOUT_ANCHOR = "                // The last row ends above OK"
ABOUT_CREDIT = '''                // AMF fork: GPL-3.0-or-later, section 5 (says what this program is based on).
                y += 20.0;
                let amf_lines = winui::paragraph(
                    &p,
                    o.x + 80.0,
                    y,
                    "Modified version, by AMF Informatica, of %s (C) Ahmed Nefzaoui. GPL-3.0-or-later.",
                    winui::MUTED(),
                    o.x + 404.0,
                    13.0,
                );
                y += 13.0 * (amf_lines as f32 - 1.0);
''' % OLD_NAME

NOTICE = f"""# AMF Download Manager

AMF Download Manager e uma versao modificada do **{OLD_NAME}** (MDM),
de Ahmed Nefzaoui: https://github.com/{OLD_REPO}

- Licenca: GNU GPL, versao 3 ou posterior (arquivo `LICENSE`), a mesma do original.
- Copyright (C) 2026 Ahmed Nefzaoui e colaboradores do {OLD_NAME}.
- Modificacoes (C) 2026 AMF Informatica, feitas em {{date}} pelo `AMF_Rebrand.py`:
  nome e sigla do programa, nomes dos executaveis e da pasta de dados, AppId e editor do
  instalador, endereco de atualizacoes/codigo-fonte/relatorios de erro (este repositorio),
  aviso de versao modificada na janela Sobre{{icon}}.
- Creditos de terceiros: `ATTRIBUTION.md`.

Este fork nao e o {OLD_NAME} oficial nem tem ligacao com o autor dele.
Quem receber o programa tem direito ao codigo-fonte: ele esta neste repositorio.
"""


def make_icons(root: Path, src: Path, dry: bool):
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("ERRO: --icon precisa do Pillow:  pip install pillow")
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    s = max(w, h)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.paste(im, ((s - w) // 2, (s - h) // 2), im)
    if s < 256:
        print(f"AVISO: {src.name} tem {s}px; o ideal e 512px ou mais.")
    sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    icons = {n: sq.resize((n, n), Image.LANCZOS) for n in sizes}
    if dry:
        return
    app = root / "crates" / "app" / "assets" / "icons" / "app"
    for n in sizes:
        icons[n].save(app / f"mdm-{n}.png")
    icons[256].save(app / "mdm.ico", sizes=[(n, n) for n in sizes],
                    append_images=[icons[n] for n in sizes if n != 256])
    ext = root / "extension" / "icons"
    for n in (16, 32, 48, 128):
        icons[n].save(ext / f"icon-{n}.png")
    art = root / "art"
    art.mkdir(exist_ok=True)
    sq.save(art / f"{NEW_NAME}.png")


def detect_repo(root: Path):
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def main():
    ap = argparse.ArgumentParser(description="Aplica a marca AMF num clone do Mister Download Manager.")
    ap.add_argument("--root", default=".", help="raiz do clone (padrao: pasta atual)")
    ap.add_argument("--repo", help="seu fork no GitHub, no formato usuario/repositorio")
    ap.add_argument("--icon", help="PNG do logo da AMF para virar o icone do programa")
    ap.add_argument("--dry-run", action="store_true", help="nao grava nada")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    dry = a.dry_run
    if not (root / "crates" / "app" / "src" / "help.rs").is_file():
        raise SystemExit(f"ERRO: {root} nao parece ser um clone do {OLD_NAME}.")
    if (root / MARKER).exists():
        raise SystemExit("Este clone ja foi convertido. Para refazer:\n"
                         "    git checkout . && git clean -fd\n  e rode o script de novo.")

    repo = a.repo or detect_repo(root)
    if not repo or not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo):
        raise SystemExit("ERRO: informe o seu fork:  --repo usuario/repositorio")
    if repo.lower() == OLD_REPO:
        raise SystemExit("ERRO: o 'origin' e o repositorio ORIGINAL. Faca um fork no GitHub, clone o SEU\n"
                         "fork (ou passe --repo usuario/repositorio): as atualizacoes e os relatorios de\n"
                         "erro do AMF nao podem apontar para o projeto do autor original.")

    stats = Stats()

    # 1) Nomes (e repositorio) em tudo o que entra no programa, no instalador e no build.
    scopes = ["crates", "extension", ".github/workflows", "Dockerfile", "docker"]
    tools = root / "tools"
    skip_tools = {"website", "readme", "icon"}
    scopes += [f"tools/{d.name}" for d in sorted(tools.iterdir()) if d.name not in skip_tools]
    short_scopes = ("tools/installer/",)
    for base in scopes:
        for p in walk(root, base):
            rel = p.relative_to(root).as_posix()
            if rel.startswith("extension/_locales/"):
                continue
            do_short = (rel.startswith("crates/") and p.suffix == ".rs") or (
                rel.startswith(short_scopes) and p.suffix in {".iss", ".isl", ".py"})
            process(p, repo, do_short, stats, dry)
    for p in sorted((root / "i18n").glob("*.tsv")):
        process(p, repo, True, stats, dry)
    extension_locales(root, repo, stats, dry)

    # 2) Trocas pontuais.
    iss = root / "tools" / "installer" / "mdm.iss"
    edit(iss, OLD_APP_ID, NEW_APP_ID, dry)
    edit(iss, "AppPublisher=Ahmed Nefzaoui", f"AppPublisher={PUBLISHER}", dry)
    edit(iss, "VersionInfoCompany=Ahmed Nefzaoui", f"VersionInfoCompany={PUBLISHER}", dry)
    edit(iss, "AppCopyright=Copyright (C) 2026 Ahmed Nefzaoui",
         f"AppCopyright=Copyright (C) 2026 Ahmed Nefzaoui ({OLD_NAME}); modified by {PUBLISHER}", dry)
    brs = root / "crates" / "app" / "build.rs"
    edit(brs, '.set("CompanyName", "Ahmed Nefzaoui")', f'.set("CompanyName", "{PUBLISHER}")', dry)
    edit(brs, '"Copyright (C) 2026 Ahmed Nefzaoui. GPL-3.0-or-later."',
         f'"Copyright (C) 2026 Ahmed Nefzaoui ({OLD_NAME}); modified by {PUBLISHER}. GPL-3.0-or-later."', dry)
    edit(root / "crates" / "app" / "src" / "help.rs", ABOUT_ANCHOR, ABOUT_CREDIT + ABOUT_ANCHOR, dry)

    # 3) Icone (opcional).
    icon_note = ""
    if a.icon:
        src = Path(a.icon).resolve()
        if not src.is_file():
            raise SystemExit(f"ERRO: nao achei o icone {src}")
        make_icons(root, src, dry)
        icon_note = ", icone do programa e da extensao"

    # 4) Avisos da GPL.
    if not dry:
        import datetime
        today = datetime.date.today().isoformat()
        (root / "AMF-NOTICE.md").write_text(
            NOTICE.replace("{date}", today).replace("{icon}", icon_note), encoding="utf-8")
        readme = root / "README.md"
        head = (f"> **AMF Download Manager**: versao modificada do {OLD_NAME}, de Ahmed Nefzaoui "
                f"(https://github.com/{OLD_REPO}), GPL-3.0-or-later. Veja [AMF-NOTICE.md](AMF-NOTICE.md). "
                "O texto abaixo e o README do projeto original.\n\n")
        readme.write_text(head + readme.read_text(encoding="utf-8"), encoding="utf-8", newline="")
        (root / MARKER).write_text(f"repo={repo}\ndate={today}\n", encoding="utf-8")

    print(f"{'[simulacao] ' if dry else ''}OK: {stats.files} arquivos alterados. Fork: {repo}")
    if not a.icon:
        print("Icone: continua o do projeto original. Para trocar, rode num clone limpo com --icon logo.png")
    print("Proximo passo: git add -A && git commit -m \"Marca AMF\" && git push")
    print("Depois, no GitHub: Actions -> Release -> Run workflow (gera o instalador do Windows).")


if __name__ == "__main__":
    sys.exit(main())
