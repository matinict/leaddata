




ffmpeg -i mF01.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 2 mF01.wav

ffmpeg -i mF01.wav -ss 00:00:25 -t 10 -ac 1 -ar 22050 mF01_clone_ref.wav



ffmpeg -i milkyInro_denoised.mp3 -acodec pcm_s16le -ar 44100 -ac 2 milkyInro_denoised.wav




Video To 1920:1080:

ffmpeg -i input.mp4 -vf scale=1920:1080 -c:a copy output.mp4




uv run --with markdown-pdf - <<EOF
from markdown_pdf import MarkdownPdf, Section
pdf = MarkdownPdf(toc_level=0)
with open("KidifyThink.md", "r") as f:
    pdf.add_section(Section(f.read()))
pdf.save("KidifyThink.pdf")
EOF







uv run --with markdown-pdf - <<EOF
from markdown_pdf import MarkdownPdf, Section
pdf = MarkdownPdf(toc_level=0)
with open("Unit-Prodcast.md", "r") as f:
    pdf.add_section(Section(f.read()))
pdf.save("Unit-Prodcast.pdf")
EOF

## The "Bulletproof" Python Script (No ToC issues)


uv run --with markdown-pdf - <<EOF
from markdown_pdf import MarkdownPdf, Section
pdf = MarkdownPdf(toc_level=0)
with open("LeadDataPlan.md", "r") as f:
    pdf.add_section(Section(f.read()))
pdf.save("output.pdf")
EOF
