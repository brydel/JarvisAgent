#!/usr/bin/env bash
# Fichiers du MODE DÉMO du Board V2 (jamais mêlés aux données réelles) : images découpées dans la maquette fournie par
# le fondateur, et vrais médias générés par ffmpeg / Python pour que lecteurs, forme d'onde et vignettes PDF soient réels.
# Idempotent. Usage : bash scripts/preparer-demo.sh (depuis studio/board-v2).
set -euo pipefail
ref="../../design/references/JARVIS_BOARD_V2_REFERENCE.png"
out="public/demo"
mkdir -p "$out"
crop() { ffmpeg -loglevel error -y -i "$ref" -vf "crop=$2:$3:$4:$5${7:+,$7},scale=$6:-2:flags=lanczos" -q:v 3 "$out/$1"; }
# zones mesurées sur la maquette (l:h:x:y) et largeur de sortie
crop montagne.jpg 386 186 139 166 960 "delogo=x=5:y=3:w=40:h=24,delogo=x=350:y=11:w=28:h=22"   # badge P2 et menu effacés
crop claude-apercu.jpg 280 129 624 165 700 "delogo=x=232:y=1:w=46:h=40"   # menu « … » effacé
crop video-maquette.jpg 298 138 638 791 1192 "delogo=x=4:y=5:w=40:h=24,delogo=x=262:y=8:w=28:h=22,delogo=x=8:y=90:w=270:h=44"   # vignette vidéo : badge, menu et titre effacés
crop ressource-1.jpg 62 46 979 870 160
crop ressource-2.jpg 62 46 1048 870 160
crop ressource-3.jpg 62 46 1118 870 160

# Audio réel (12 s) : accord doux modulé, MP3 — sa forme d'onde est calculée du fichier par le navigateur.
ffmpeg -loglevel error -y -f lavfi -i "sine=f=220:d=12" -f lavfi -i "sine=f=330:d=12" -f lavfi -i "anoisesrc=d=12:a=0.04" \
  -filter_complex "[0][1][2]amix=inputs=3,volume='0.6+0.4*sin(2*PI*t*0.7)':eval=frame,afade=t=in:d=0.4,afade=t=out:st=11.4:d=0.6" \
  -ac 1 -ar 44100 -b:a 96k "$out/reunion-ideation.mp3"
# Vidéo réelle (6 s) : lent zoom sur la vignette de la maquette, MP4 H.264 ; vignette extraite de la vidéo.
ffmpeg -loglevel error -y -loop 1 -i "$out/video-maquette.jpg" -t 6 -r 30   -vf "scale=1480:-2,zoompan=z='min(zoom+0.0008,1.08)':d=180:s=740x342:fps=30,format=yuv420p"   -c:v libx264 -preset veryfast -crf 28 -movflags +faststart "$out/presentation-produit.mp4"
ffmpeg -loglevel error -y -ss 1 -i "$out/presentation-produit.mp4" -frames:v 1 -q:v 3 "$out/video-vignette.jpg"
# Même vidéo en WebM (VP9) : lisible par tous les Chromium, y compris ceux sans décodeur H.264 (Playwright).
ffmpeg -loglevel error -y -i "$out/presentation-produit.mp4" -c:v libvpx-vp9 -b:v 0 -crf 40 -deadline good -cpu-used 4 -an "$out/presentation-produit.webm"
rm -f "$out/video-maquette.jpg" "$out/pdf-page-1.jpg" "$out/pdf-page-2.jpg"
# PDF réel de 2 pages (texte), rendu par pdf.js dans la carte.
python3 - "$out/plan-produit.pdf" <<'EOF'
import sys
pages = [["Plan produit v1.0", "", "Vision : un studio d'agents fiable.", "Roadmap : Board V2, missions, agents.",
          "Jalons : M2 Studio, M3 executants."],
         ["Maquettes initiales", "", "Board spatial multimedia", "Panneau contextuel", "Approbations humaines"]]
objs, kids = [], []
def add(s): objs.append(s); return len(objs)
font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
for lignes in pages:
    flux = "BT /F1 22 Tf 60 760 Td " + " ".join(f"({l}) Tj 0 -34 Td" for l in lignes) + " ET"
    c = add(f"<< /Length {len(flux)} >>\nstream\n{flux}\nendstream")
    kids.append(add(f"<< /Type /Page /Parent PAGES /MediaBox [0 0 612 792] /Contents {c} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>"))
pages_id = add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>")
cat = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
out, off = b"%PDF-1.4\n", []
for i, o in enumerate(objs, 1):
    off.append(len(out)); out += f"{i} 0 obj\n{o.replace('PAGES', f'{pages_id} 0 R')}\nendobj\n".encode("latin-1")
x = len(out)
out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in off)
out += f"trailer << /Size {len(objs)+1} /Root {cat} 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
open(sys.argv[1], "wb").write(out)
EOF
ls -la "$out"
