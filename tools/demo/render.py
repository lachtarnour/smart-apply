"""Edit native captures into a narrated, captioned 1080p MP4.

Requires Pillow, PyMuPDF, imageio-ffmpeg and a macOS French voice.
All spotlights and explanation cards are composited here, never in the app.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import pymupdf
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
W, H, FPS = 1920, 1080, 24
SCALE, LEFT, TOP = 1.1, 80, 70
ACCENT = "#A991FF"
GOLD = "#FFCB67"
FONT = "/System/Library/Fonts/Avenir Next.ttc"


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=2 if bold else 7)


def wrapped(draw, value, face, width):
    lines = []
    for paragraph in value.split("\n"):
        line = ""
        for word in paragraph.split():
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=face) > width and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


SCENES = [
    dict(
        shot="01-home",
        chapter="Bienvenue",
        title="Votre recherche,\nun seul espace.",
        intro=True,
        body="Trouver des offres.\nPréparer ses candidatures.",
        narration="Élan. Votre recherche d’emploi, centralisée.",
        min_duration=2.5,
    ),
    dict(
        shot="01-home",
        chapter="01 / Accueil",
        title="Tout commence ici",
        pos=(440, 430),
        body="• Offres à analyser\n• Candidatures prêtes ou envoyées",
        narration="Suivez vos offres et vos candidatures.",
    ),
    dict(
        shot="02-search",
        chapter="02 / Rechercher",
        title="Une recherche ciblée",
        pos=(510, 620),
        body="• Poste, ville et source\n• Limite : 3 annonces",
        narration="Choisissez vos critères. Limitez à trois annonces.",
    ),
    dict(
        shot="03-fetch",
        chapter="02 / Récupérer",
        title="Les offres arrivent",
        pos=(510, 745),
        focus=[250, 85, 1310, 305],
        body="• Récupération des annonces\n• Enregistrement et filtrage",
        narration="Récupérez, enregistrez et filtrez les offres.",
    ),
    dict(
        shot="04-duplicates",
        chapter="03 / Repérer les doublons",
        title="Deux doublons repérés",
        pos=(860, 745),
        focus=[250, 95, 385, 315],
        body="• 2 annonces déjà connues\n• Comparaison entre sources",
        narration="Deux doublons détectés. Comparez les sources.",
    ),
    dict(
        shot="05-compare",
        chapter="03 / Comparer",
        title="Confirmer le doublon",
        pos=(240, 655),
        focus=[680, 155, 860, 525],
        body="• Vérifiez le poste et le contenu\n• « Même offre » : regrouper",
        narration="Même offre : regroupez les deux versions.",
    ),
    dict(
        shot="06-second-duplicate",
        chapter="03 / Traiter le second",
        title="Traiter le second",
        pos=(240, 655),
        focus=[680, 155, 860, 525],
        body="• Confirmez aussi le second\n• Offres distinctes : garder les deux",
        narration="Confirmez le second doublon. Gardez séparément les postes distincts.",
    ),
    dict(
        shot="07-resolved",
        chapter="03 / Terminé",
        title="La liste est nettoyée",
        pos=(630, 675),
        focus=[650, 350, 500, 200],
        body="• 0 doublon en attente\n• 3 offres distinctes",
        narration="Trois offres distinctes. Aucun doublon restant.",
    ),
    dict(
        shot="08-offers",
        chapter="04 / Explorer une offre",
        title="Tout le détail du poste",
        pos=(360, 605),
        focus=[932, 28, 643, 325],
        body="• Description du poste\n• Analyse selon votre profil",
        narration="Consultez l’offre. Lancez son analyse.",
    ),
    dict(
        shot="09-analysis",
        chapter="04 / Comprendre le résultat",
        title="Un résultat expliqué",
        pos=(360, 545),
        focus=[932, 28, 643, 350],
        body="• Points de correspondance\n• Éléments à vérifier",
        narration="Repérez vos atouts et les points à vérifier.",
    ),
    dict(
        shot="10-generation",
        chapter="05 / Créer le dossier",
        title="Un clic pour les documents",
        pos=(370, 550),
        focus=[932, 780, 642, 94],
        body="• CV adapté au poste\n• Lettre de motivation",
        narration="Créer génère le CV et la lettre.",
    ),
    dict(
        shot="11-documents",
        chapter="05 / Dossier prêt",
        title="Documents disponibles",
        pos=(370, 550),
        focus=[932, 780, 642, 94],
        body="• CV et lettre en PDF\n• Accès depuis l’offre",
        narration="Ouvrez les documents depuis l’offre.",
    ),
    dict(
        pdf="cv_pdf",
        chapter="06 / Le CV généré",
        title="Un CV adapté\nau poste",
        body="• Titre ciblé\n• Compétences pertinentes\n• Expériences du profil",
        narration="Le CV met en avant les compétences pertinentes.",
        min_duration=4.5,
    ),
    dict(
        pdf="motivation_letter_pdf",
        chapter="06 / La lettre générée",
        title="Une lettre\ncontextualisée",
        body="• Parcours relié aux missions\n• Lettre prête à relire",
        narration="La lettre relie votre parcours aux missions.",
        min_duration=4.5,
    ),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=REPO / "data/demo")
    parser.add_argument("--output", type=Path, default=REPO / "output/demo")
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument(
        "--audio-dir", type=Path, help="Use prepared 01.wav, 02.wav… narration clips"
    )
    parser.add_argument("--voice", default="Eddy (Français (France))")
    parser.add_argument("--rate", type=int, default=205, help="Narration words per minute")
    args = parser.parse_args()
    runtime, output = args.runtime.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = output / "montage"
    work.mkdir(exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    manifest = {s["name"]: s for s in json.loads((runtime / "capture-manifest.json").read_text())}
    audit = json.loads((runtime / "audit.json").read_text())
    documents = {d["type"]: d["path"] for d in audit["application"]["documents"]}
    backgrounds, overlays, audio_paths, durations = [], [], [], []
    for i, scene in enumerate(SCENES):
        base = Image.new("RGB", (W, H), "#0B0A12")
        draw = ImageDraw.Draw(base)
        draw.text((80, 17), "ÉLAN", font=font(25, True), fill="#EAE5FF")
        draw.text((235, 20), scene["chapter"], font=font(23), fill="#C1B8D5")
        label = "DÉMONSTRATION · DONNÉES FICTIVES"
        draw.text(
            (W - 80 - draw.textlength(label, font=font(17)), 24),
            label,
            font=font(17),
            fill="#8E879D",
        )
        layer = Image.new("RGBA", (W, H))
        ld = ImageDraw.Draw(layer)
        if "pdf" in scene:
            with pymupdf.open(documents[scene["pdf"]]) as doc:
                assert len(doc) == 1, f"{scene['pdf']}: expected one page, got {len(doc)}"
                page = doc[0]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                pdf = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pdf.save(work / f"{i + 1:02}-document.png")
                text = page.get_text()
                assert "Camille" in text and len(text) > 600
            pdf.thumbnail((725, 970), Image.Resampling.LANCZOS)
            px, py = 1080, 78
            draw.rounded_rectangle(
                (px - 8, py - 8, px + pdf.width + 8, py + pdf.height + 8), radius=10, fill="#2B2638"
            )
            base.paste(pdf, (px, py))
            ld.text((140, 270), scene["title"], font=font(68, True), fill="#F3EFFF", spacing=6)
            lines = wrapped(ld, scene["body"], font(30), 720)
            for j, line in enumerate(lines):
                ld.text((145, 465 + j * 43), line, font=font(30), fill="#BDB4CF")
            ld.rounded_rectangle((145, 700, 565, 750), radius=25, fill="#2B2244")
            ld.text((170, 708), "PDF réellement généré par Élan", font=font(22), fill="#CCB8FF")
        else:
            shot = manifest[scene["shot"]]
            native = (
                Image.open(shot["image"])
                .convert("RGB")
                .resize((1760, 990), Image.Resampling.LANCZOS)
            )
            base.paste(native, (LEFT, TOP))
            if scene.get("intro"):
                shade = Image.new("RGBA", (1760, 990), (8, 6, 15, 225))
                layer.alpha_composite(shade, (LEFT, TOP))
                ld.text((200, 265), scene["title"], font=font(100, True), fill="#F4EFFF", spacing=5)
                ld.line((207, 553, 390, 553), fill=ACCENT, width=5)
                ld.multiline_text(
                    (207, 590), scene["body"], font=font(34), fill="#C7BED8", spacing=12
                )
                ld.text(
                    (207, 850),
                    "Application native · Base dédiée · Collecte et réponses IA simulées",
                    font=font(23),
                    fill="#8E859F",
                )
            else:
                focus = scene.get("focus", shot.get("focus"))
                veil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                vd = ImageDraw.Draw(veil)
                vd.rectangle((LEFT, TOP, LEFT + 1760, TOP + 990), fill=(3, 2, 8, 110))
                x, y, w, h = focus
                box = (
                    LEFT + int(x * SCALE) - 5,
                    TOP + int(y * SCALE) - 5,
                    LEFT + int((x + w) * SCALE) + 5,
                    TOP + int((y + h) * SCALE) + 5,
                )
                vd.rounded_rectangle(box, radius=17, fill=(0, 0, 0, 0), outline=GOLD, width=3)
                layer.alpha_composite(veil)
                cx, cy = scene["pos"]
                cardw = 530
                lines = wrapped(ld, scene["body"], font(26), cardw - 64)
                cardh = 110 + len(lines) * 36
                assert cy + cardh < 1055, (i, cy, cardh)
                ld.rounded_rectangle(
                    (cx + 5, cy + 10, cx + cardw + 5, cy + cardh + 10),
                    radius=23,
                    fill=(0, 0, 0, 65),
                )
                ld.rounded_rectangle((cx, cy, cx + cardw, cy + cardh), radius=23, fill="#FAF9FC")
                ld.ellipse((cx + 28, cy + 28, cx + 66, cy + 66), fill=GOLD)
                count = str(i)
                ld.text(
                    (cx + 47 - ld.textlength(count, font=font(21, True)) / 2, cy + 31),
                    count,
                    font=font(21, True),
                    fill="#382714",
                )
                ld.text((cx + 82, cy + 30), scene["title"], font=font(28, True), fill="#24202D")
                for j, line in enumerate(lines):
                    ld.text((cx + 32, cy + 86 + j * 36), line, font=font(26), fill="#645E70")
        backgrounds.append(base)
        overlays.append(layer)
        preview = Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")
        preview.save(work / f"{i + 1:02}-preview.jpg", quality=94)
        if args.preview_only:
            continue
        speech = work / f"{i + 1:02}.txt"
        speech_config = work / f"{i + 1:02}-speech.json"
        signature = json.dumps(
            dict(text=scene["narration"], voice=args.voice, rate=args.rate),
            ensure_ascii=False,
            sort_keys=True,
        )
        narration_changed = not speech_config.exists() or speech_config.read_text() != signature
        speech.write_text(scene["narration"])
        aiff = work / f"{i + 1:02}.aiff"
        wav = work / f"{i + 1:02}.wav"
        if args.audio_dir:
            audio_source = args.audio_dir.resolve() / f"{i + 1:02}.wav"
            if not audio_source.is_file():
                raise RuntimeError(f"Missing narration: {audio_source}")
        else:
            if narration_changed or not aiff.exists() or aiff.stat().st_size < 5000:
                subprocess.run(
                    [
                        "say",
                        "-v",
                        args.voice,
                        "-r",
                        str(args.rate),
                        "-f",
                        str(speech),
                        "-o",
                        str(aiff),
                    ],
                    check=True,
                )
            audio_source = aiff
        subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(audio_source),
                *(
                    [
                        "-af",
                        "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB:"
                            "start_silence=0.06:stop_periods=-1:stop_duration=0.25:"
                            "stop_threshold=-50dB:stop_silence=0.12",
                    ]
                    if args.audio_dir
                    else []
                ),
                "-ar",
                "48000",
                "-ac",
                "1",
                str(wav),
            ],
            check=True,
        )
        with wave.open(str(wav)) as audio:
            data = audio.readframes(audio.getnframes())
            duration = audio.getnframes() / audio.getframerate()
            assert duration > 1, "Speech did not produce a usable audio clip"
        if not args.audio_dir:
            speech_config.write_text(signature)
        duration = math.ceil(max(duration + 0.55, scene.get("min_duration", 3.0)) * FPS) / FPS
        audio_paths.append((data, duration))
        durations.append(duration)
        print(f"VOICE {i + 1:02} {duration:.2f}s", flush=True)
    if args.preview_only:
        return
    narration = work / "narration.wav"
    with wave.open(str(narration), "wb") as joined:
        joined.setnchannels(1)
        joined.setsampwidth(2)
        joined.setframerate(48000)
        for data, duration in audio_paths:
            lead = b"\x00" * int(0.18 * 48000) * 2
            padding = b"\x00" * (int(round(duration * 48000)) * 2 - len(data) - len(lead))
            joined.writeframes(lead + data + padding)
    target = output / "Elan-demo.mp4"
    command = [
        ffmpeg,
        "-v",
        "warning",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
        "-i",
        str(narration),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=7",
        "-ar",
        "48000",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(target),
    ]
    with (work / "encode.log").open("w") as log:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        total = sum(round(d * FPS) for d in durations)
        current = 0
        for i, (base, overlay, duration) in enumerate(
            zip(backgrounds, overlays, durations, strict=True)
        ):
            finished = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
            for frame in range(round(duration * FPS)):
                fade = min(1, frame / 9)
                image = Image.blend(base, finished, fade) if fade < 1 else finished.copy()
                draw = ImageDraw.Draw(image)
                # Animated cursor indicates the real control activated in the capture.
                shot = manifest.get(SCENES[i].get("shot", ""), {})
                if shot.get("cursor") and not SCENES[i].get("intro"):
                    x, y, w, h = shot["cursor"]
                    ease = min(1, max(0, (frame / FPS - 0.7) / 1.1))
                    ease = 1 - (1 - ease) ** 3
                    tx = LEFT + (x + w * 0.6) * SCALE
                    ty = TOP + (y + h * 0.6) * SCALE
                    px = tx - 90 * (1 - ease)
                    py = ty + 38 * (1 - ease)
                    if frame / FPS > duration - 0.9:
                        radius = 10 + int(18 * ((frame / FPS - (duration - 0.9)) / 0.9))
                        draw.ellipse(
                            (px - radius, py - radius, px + radius, py + radius),
                            outline=GOLD,
                            width=2,
                        )
                    draw.polygon(
                        [
                            (px, py),
                            (px + 2, py + 26),
                            (px + 10, py + 18),
                            (px + 17, py + 31),
                            (px + 22, py + 28),
                            (px + 15, py + 16),
                            (px + 26, py + 15),
                        ],
                        fill="white",
                        outline="#423752",
                        width=2,
                    )
                draw.line((80, 1071, 1840, 1071), fill="#2B233A", width=4)
                draw.line((80, 1071, 80 + int(1760 * current / total), 1071), fill=ACCENT, width=4)
                proc.stdin.write(image.tobytes())
                current += 1
            print(f"ENCODE {i + 1:02}/{len(SCENES)}", flush=True)
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError((work / "encode.log").read_text())
    (output / "timeline.json").write_text(
        json.dumps(
            [dict(**scene, duration=d) for scene, d in zip(SCENES, durations, strict=True)],
            ensure_ascii=False,
            indent=2,
        )
    )

    def stamp(seconds):
        ms = round(seconds * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    t = 0
    srt = []
    for i, (scene, duration) in enumerate(zip(SCENES, durations, strict=True), 1):
        srt.append(f"{i}\n{stamp(t)} --> {stamp(t + duration)}\n{scene['narration']}\n")
        t += duration
    (output / "Elan-demo.fr.srt").write_text("\n".join(srt))
    backgrounds[0] = Image.alpha_composite(backgrounds[0].convert("RGBA"), overlays[0]).convert(
        "RGB"
    )
    backgrounds[0].save(output / "affiche.jpg", quality=95)
    print(f"VIDEO {target} · {t:.2f}s · {target.stat().st_size / 1024**2:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
