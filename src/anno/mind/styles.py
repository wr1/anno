from pathlib import Path

STYLE_COMMON = (
    ' branchmargin="100" branchradius="25" linktype="straight" linkwidth="4" linkarrow="false"'
    ' linkdash="solid" nodeborder="underlined" nodewidth="200" nodeborderwidth="4" nodefill="false"'
    ' nodemargin="8" nodepadding="6" nodefont="Sans 11" nodemarkup="true" connectiondash="dotted"'
    ' connectionlwidth="2" connectionarrow="fromto" connectionpadding="3" connectionfont="Sans 10"'
    ' connectiontwidth="100" calloutfont="Sans 12" calloutpadding="5" calloutptrwidth="20"'
    ' calloutptrlength="20"'
)
MINDER_STYLES = (
    '<style level="0" isset="false" branchmargin="100" branchradius="25" linktype="straight"'
    ' linkwidth="4" linkarrow="false" linkdash="solid" nodeborder="rounded" nodewidth="200"'
    ' nodeborderwidth="4" nodefill="false" nodemargin="10" nodepadding="10" nodefont="Sans 11"'
    ' nodemarkup="true" connectiondash="dotted" connectionlwidth="2" connectionarrow="fromto"'
    ' connectionpadding="3" connectionfont="Sans 10" connectiontwidth="100" calloutfont="Sans 12"'
    ' calloutpadding="5" calloutptrwidth="20" calloutptrlength="20"/>'
    + "".join(f'<style level="{i}" isset="false"{STYLE_COMMON}/>' for i in range(1, 11))
)


def make_minder_file(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0"?>\n'
        '<minder version="1.16.2" parent-etag="0" etag="0">\n'
        '  <theme name="dark" label="Dark" index="1"/>\n'
        f"  <styles>{MINDER_STYLES}</styles>\n"
        "  <images/>\n"
        "  <nodes/>\n"
        "  <selected-nodes/>\n"
        "  <groups/>\n"
        "  <stickers/>\n"
        '  <nodelinks id="0"/>\n'
        "</minder>\n"
    )
