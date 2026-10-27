#!/usr/bin/env python3
"""Build the compact, branded SonarQube operations guide. Requires ReportLab."""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "MyScoutee_SonarQube_Guide_EN.pdf"
for name, file in [("Guide", "DejaVuSans.ttf"), ("GuideBold", "DejaVuSans-Bold.ttf"),
                   ("GuideMono", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, "/usr/share/fonts/truetype/dejavu/" + file))

NAVY = colors.HexColor("#17324d")
BLUE = colors.HexColor("#176b87")
MUTED = colors.HexColor("#586675")
SOFT = colors.HexColor("#f3f6f8")
LINE = colors.HexColor("#d9e1e8")
INK = colors.HexColor("#1c2633")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Body", fontName="Guide", fontSize=9.2, leading=14, textColor=INK, spaceAfter=9))
styles.add(ParagraphStyle("TitleGuide", fontName="GuideBold", fontSize=27, leading=33, textColor=NAVY, spaceAfter=14))
styles.add(ParagraphStyle("SectionGuide", fontName="GuideBold", fontSize=15, leading=20, textColor=NAVY, spaceBefore=13, spaceAfter=9))
styles.add(ParagraphStyle("KickerGuide", fontName="GuideBold", fontSize=8.5, leading=13, textColor=BLUE, spaceAfter=8))
styles.add(ParagraphStyle("SmallGuide", parent=styles["Body"], fontSize=8, leading=11, textColor=MUTED))
styles.add(ParagraphStyle("CellGuide", parent=styles["Body"], fontSize=8, leading=12, spaceAfter=0))
styles.add(ParagraphStyle("CodeGuide", fontName="GuideMono", fontSize=7.4, leading=11, textColor=NAVY,
                          backColor=SOFT, borderPadding=10, spaceBefore=5, spaceAfter=14))


def p(text, style="Body"):
    return Paragraph(text, styles[style])


def table(rows, widths, header=True):
    content = [[p(str(cell), "CellGuide") for cell in row] for row in rows]
    result = Table(content, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    commands = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), SOFT)]
    result.setStyle(TableStyle(commands))
    return result


def code(text):
    return Preformatted(text, styles["CodeGuide"])


def frame(canvas, document):
    width, height = A4
    canvas.saveState()
    if document.page == 1:
        canvas.drawImage(str(ROOT / "assets/heart.png"), 46, height - 77, width=43, height=43, mask="auto")
        canvas.setFont("GuideBold", 20)
        canvas.setFillColor(NAVY)
        canvas.drawString(95, height - 56, "yScoutee")
        canvas.setFont("Guide", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(96, height - 70, "Engineering documentation")
    else:
        canvas.setFont("GuideBold", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(46, height - 35, "MYSCOUTEE  /  ENGINEERING")
    canvas.setStrokeColor(LINE)
    canvas.line(46, 40, width - 46, 40)
    canvas.setFont("Guide", 7.4)
    canvas.drawString(46, 27, "MSC-SQ-001  |  Version 1.2  |  2026-10-23")
    canvas.drawRightString(width - 46, 27, str(document.page))
    canvas.restoreState()


story = [
    p("CODE QUALITY / LOCAL OPERATIONS", "KickerGuide"),
    p("SonarQube Guide", "TitleGuide"),
    p("One shared server. Repository-owned analysis configuration. Explicit, manually scheduled scans."),
    Spacer(1, 10),
    table([["Document", "Scope"], ["MSC-SQ-001 / 1.2 / EN", "Backend, Template, Base and Components"],
           ["Tool repository", "myscoutee-sonarqube"],
           ["Runtime", "Pinned SonarQube Community Build, PostgreSQL and SonarScanner Docker images"]], [178, 325]),
    p("Start from the shared repository", "SectionGuide"),
    p("The source repository is an explicit argument. Its normal application startup, builds and tests remain independent."),
    code("cd ../myscoutee-sonarqube\n./run.sh ../myscoutee-backend check\n./run.sh ../myscoutee-backend up\n./run.sh ../myscoutee-backend scan backend\n./run.sh ../myscoutee-backend stop"),
    p("Replace the source argument to select another project for analysis. "
      "All projects use the same dashboard at <b>localhost:9000</b>. Scans never start another server."),
    p("First use on a new machine", "SectionGuide"),
    p("Run <b>init</b> once for the shared server. It creates a private database password. Start the instance, "
      "change the initial admin password in its UI, and store an analysis token in the existing ignored .state/myscoutee/.env file. "
      "Existing migrated credentials are retained; init never overwrites them."),
    p("Linux prerequisite: vm.max_map_count must be at least 524288. If needed, explicitly run "
      "<b>sudo bash setup-host.sh</b> on the Docker host. The helper preserves higher values and persists the setting."),
    PageBreak(),
    p("Configuration and analysis inputs", "TitleGuide"),
    p("Keep ownership clear", "SectionGuide"),
    table([["Location", "Contents"],
           ["Application / config/sonarqube/project.json", "Analysis ID and owned module base directories; no server lifecycle settings."],
           ["Application / config/sonarqube/", "backend, frontend, components and microservices .properties files; project keys and source rules."],
           ["Shared tool / server.json", "One server identity, Compose project and loopback port for every analysis."],
           ["Shared tool / .state/&lt;id&gt;/", "Separate bytecode, scanner cache and reports. Only .state/myscoutee/.env owns shared credentials."]], [220, 283]),
    p("Choose the analysis scope", "SectionGuide"),
    code("./run.sh ../myscoutee-backend scan backend\n./run.sh ../myscoutee-backend scan microservices\n./run.sh ../myscoutee-backend scan frontend\n./run.sh ../myscoutee-components scan components\n./run.sh ../myscoutee-base scan backend"),
    p("<b>scan all</b> runs the selected repository's configured modules serially. It is an explicit broad operation; select individual modules "
      "when other contributors own frontend or components work. The runner never starts a server or executes a build or test implicitly."),
    p("Java bytecode and coverage", "SectionGuide"),
    p("Build matching artifacts manually through the application repository's existing build owner. Use the existing Spring Boot JAR for backend and communication assembly JAR for microservices. "
      "BACKEND_JAR and MICROSERVICES_JAR select another artifact. Stale inputs stop the scan."),
    code("BACKEND_COVERAGE_REPORT=server/projects/profile/build/junit/reports/jacoco.xml \\\n  ./run.sh ../myscoutee-backend scan backend\n\nMICROSERVICES_COVERAGE_REPORT=microservices/build/bootstrap-tests/reports/jacoco.xml \\\n  ./run.sh ../myscoutee-backend scan microservices"),
    p("Base: explicitly run <b>./gradlew prepareSonar --parallel</b> from base/server. Paths resolve against the source repository. Coverage is imported "
      "only when explicitly supplied. Missing, malformed or stale reports stop the scan; no tests are started to replace them.", "SmallGuide"),
    PageBreak(),
    p("Resources, history and findings", "TitleGuide"),
    p("Schedule one substantial analysis batch", "SectionGuide"),
    p("Fix complete rule families and validate them with focused checks before launching another full scan. "
      "The central scan lock covers both applications, artifact preparation and server-side processing, preventing "
      "overlapping central scanner runs. Application resource and watcher rules still apply."),
    table([["Container", "Memory limit", "CPU limit"],
           ["SonarQube server", "4 GiB", "4"], ["PostgreSQL", "512 MiB", "1"],
           ["One-shot scanner", "4 GiB", "6"]], [250, 145, 108]),
    Spacer(1, 10),
    p("Keep capacity for the shared server and one scanner together. Limits can be overridden explicitly; CPU quotas do not pin cores. Historical stopped servers retain "
      "their volumes without consuming server memory. Scanner Java heap is capped at 1536 MiB; TypeScript analysis uses a 2048 MiB Node heap."),
    p("Preserve history; stop deliberately", "SectionGuide"),
    code("./run.sh ../myscoutee-backend status\n./run.sh ../myscoutee-backend logs\n./run.sh ../myscoutee-backend stop\n./run.sh ../myscoutee-backend up"),
    p("The shared server retains the existing myscoutee-sonarqube Compose name and volumes. "
      "The old template database and credentials remain untouched; their history is not automatically merged. <b>stop</b> retains containers and data; "
      "<b>down</b> removes the shared server's containers/network while retaining volumes. Automatic restart is disabled."),
    p("Interpret the result correctly", "SectionGuide"),
    p("A successful scanner upload and server processing confirm that analysis completed. A passing Quality Gate "
      "confirms only the gate's configured conditions; it does not mean zero overall findings. Track Security, Reliability, "
      "Maintainability, coverage and duplication separately, comparing the same source scope."),
    p("Reviewed findings are separate from repaired defects. REVIEWED_FINDINGS.md records the narrow, tested "
      "service-only CSRF exception. Other findings remain actionable; neither thresholds nor broad exclusions should "
      "be changed to present an incomplete cleanup as complete."),
    p("Preparation remains outside the application lifecycle", "SectionGuide"),
    p("Sources are mounted read-only. Helm analysis reuses the deployment owner's chart values with isolated "
      "placeholder credentials and disposable Git provenance. It does not contact the lab VM or alter source history. "
      "Generated artifacts, runtime credentials and scanner caches stay in the shared repository's ignored private state.", "SmallGuide"),
]

if __name__ == "__main__":
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=46, rightMargin=46,
                                 topMargin=106, bottomMargin=52,
                                 title="MyScoutee SonarQube Guide", author="MyScoutee / fssrepository")
    document.build(story, onFirstPage=frame, onLaterPages=frame)
    print(OUTPUT)
