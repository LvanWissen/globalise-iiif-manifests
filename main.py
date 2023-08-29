import os
from dataclasses import dataclass

import iiif_prezi3
import requests
from lxml import etree as ET


@dataclass
class Fonds:
    code: str
    title: str
    uri: str
    hasPart: list


@dataclass
class Series:
    code: str
    title: str
    uri: str
    hasPart: list


@dataclass
class FileGroup:
    code: str
    title: str
    hasPart: list


@dataclass
class File:
    code: str
    title: str
    uri: str
    date: str
    metsid: str


def to_collection(
    i,
    base_url,
    prefix="",
    language="en",
):
    collection_filename = f"{prefix}{i.code}.json"
    collection_filename = collection_filename.replace(" ", "+")
    collection_id = base_url + collection_filename

    dirname = os.path.dirname(collection_filename)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    iiif_prezi3.config.configs["helpers.auto_fields.AutoLang"].auto_lang = language

    collection = iiif_prezi3.Collection(
        id=collection_id,
        label=i.code,
        metadata=[
            iiif_prezi3.KeyValueString(
                label="Identifier",
                value={"en": [i.code]},
            ),
            iiif_prezi3.KeyValueString(
                label="Title",
                value={"en": [i.title]},
            ),
            iiif_prezi3.KeyValueString(
                label="Permalink",
                value={"en": [f'<a href="{i.uri}">{i.uri}</a>']},
            ),
        ],
    )

    for c in i.hasPart:
        if isinstance(c, Series):
            collection.add_item(
                to_collection(
                    c, base_url, prefix=collection_filename.replace(".json", "/")
                )
            )
        elif isinstance(c, FileGroup):
            collection.add_item(
                to_collection(
                    c,
                    base_url,
                    prefix=collection_filename.replace(".json", "/"),
                )
            )  # or manifest?
        elif isinstance(c, File):
            collection.add_item(
                to_manifest(
                    c,
                    base_url,
                    prefix=collection_filename.replace(".json", "/"),
                )
            )

        break

    with open(collection_filename, "w") as outfile:
        outfile.write(collection.json(indent=4))

    return collection


def to_manifest(
    i,
    base_url,
    prefix="",
    license_uri="https://creativecommons.org/publicdomain/mark/1.0/",
    language="en",
):
    manifest_filename = f"{prefix}{i.code}.json"
    manifest_filename = manifest_filename.replace(" ", "+")
    manifest_id = base_url + manifest_filename

    os.makedirs(os.path.dirname(manifest_filename), exist_ok=True)

    iiif_prezi3.config.configs["helpers.auto_fields.AutoLang"].auto_lang = language

    manifest = iiif_prezi3.Manifest(
        id=manifest_id,
        label=i.code,
        metadata=[
            iiif_prezi3.KeyValueString(
                label="Identifier",
                value={"en": [i.code]},
            ),
            iiif_prezi3.KeyValueString(
                label="Title",
                value={"en": [i.title]},
            ),
            iiif_prezi3.KeyValueString(
                label="Date",
                value={"en": [i.date or "?"]},
            ),
            iiif_prezi3.KeyValueString(
                label="Permalink",
                value={"en": [f'<a href="{i.uri}">{i.uri}</a>']},
            ),
        ],
        # seeAlso={"id": i.uri, "label": "Permalink"},
        rights=license_uri,
    )

    scans = get_scans(i.metsid)

    for n, (file_name, iiif_service) in enumerate(scans, 1):
        manifest.make_canvas_from_iiif(
            url=iiif_service,
            id=f"{manifest_id}/canvas/p{n}",
            label=file_name,
            anno_id=f"{manifest_id}/canvas/p{n}/anno",
            anno_page_id=f"{manifest_id}/canvas/p{n}/annotationpage",
            metadata=[
                iiif_prezi3.KeyValueString(
                    label="Scan",
                    value={"en": [file_name]},
                )
            ],
        )

    with open(manifest_filename, "w") as outfile:
        outfile.write(manifest.json(indent=4))

    return manifest


def get_scans(metsid):
    NS = {"mets": "http://www.loc.gov/METS/"}

    if metsid:
        url = "https://service.archief.nl/gaf/api/mets/v1/" + metsid
        xml = requests.get(url).text
        mets = ET.fromstring(bytes(xml, encoding="utf-8"))

        scans = []

        for file_el in mets.findall(
            "mets:fileSec/mets:fileGrp[@USE='DISPLAY']/mets:file",
            namespaces=NS,
        ):
            file_id = file_el.attrib["ID"][:-3]  # without IIP
            service_url = file_el.find(
                "./mets:FLocat[@LOCTYPE='URL']",
                namespaces=NS,
            ).attrib["{http://www.w3.org/1999/xlink}href"]

            file_name = (
                mets.find(
                    "mets:structMap/mets:div/mets:div[@ID='" + file_id + "']",
                    namespaces=NS,
                )
                .attrib["LABEL"]
                .split("/")[-1]
            )

            scans.append((file_name, service_url))

    return scans


def parse_ead(ead_file_path: str):
    tree = ET.parse(ead_file_path)

    fonds_code = tree.find("eadheader/eadid").text
    fonds_title = tree.find("eadheader/filedesc/titlestmt/titleproper").text
    permalink = tree.find("eadheader/eadid[@url]").attrib["url"]

    fonds = Fonds(
        code=fonds_code,
        title=fonds_title,
        uri=permalink,
        hasPart=[],
    )

    series_els = tree.findall(".//c[@level='series']")
    for series_el in series_els:
        s = get_series(series_el)
        fonds.hasPart.append(s)

    return fonds


def get_series(series_el):
    series_code = series_el.find("did/unitid[@type='series_code']")
    series_title = "".join(series_el.find("did/unittitle").itertext()).strip()
    if series_code is not None:
        series_code = series_code.text
    else:
        series_code = series_title

    s = Series(
        code=series_code,
        title=series_title,
        uri="",
        hasPart=[],
    )

    file_and_filegrp_els = series_el.xpath("child::*")
    for el in file_and_filegrp_els:
        if el.get("level") == "file":
            i = get_file(el)

        elif el.get("otherlevel") == "filegrp":
            i = get_filegrp(el)

        elif el.get("level") == "subseries":
            i = get_series(el)
        else:
            continue

        s.hasPart.append(i)

    return s


def get_filegrp(filegrp_el):
    filegrp_code = filegrp_el.find("did/unitid").text
    filegrp_title = "".join(filegrp_el.find("did/unittitle").itertext()).strip()

    while "  " in filegrp_title:  # double space
        filegrp_title = filegrp_title.replace("  ", " ")

    filegrp = FileGroup(
        code=filegrp_code,
        title=filegrp_title,
        hasPart=[],
    )

    file_els = filegrp_el.findall("c[@level='file']")
    for file_el in file_els:
        f = get_file(file_el)
        filegrp.hasPart.append(f)

    return f


def get_file(file_el):
    did = file_el.find("did")

    # Inventory number
    inventorynumber_el = did.find("unitid[@identifier]")
    if inventorynumber_el is not None:
        inventorynumber = inventorynumber_el.text
    else:
        inventorynumber = ""

    # URI
    permalink = did.find("unitid[@type='handle']").text

    # Title
    title = "".join(did.find("unittitle").itertext())
    while "  " in title:  # double space
        title = title.replace("  ", " ")

    # Date
    date_el = did.find("unitdate")
    if date_el is not None:
        date = date_el.attrib.get("normal", date_el.attrib.get("text"))
    else:
        date = ""

    # METS id
    metsid_el = did.find("dao")
    if metsid_el is not None:
        metsid = metsid_el.attrib["href"].split("/")[-1]
    else:
        metsid = ""

    f = File(
        code=inventorynumber,
        title=title,
        uri=permalink,
        date=date,
        metsid=metsid,
    )

    return f


def main(
    ead_file_path: str,
    base_url: str,
) -> None:
    """
    Generate IIIF Collections and Manifests from an EAD file.

    The lowest level of these collections are manifests for each inventory.

    Args:
        ead_file_path (str): File path to the EAD file of a specific archive
        collection_number (str): The collection number of this archive
        collection_label (str): The title of this archive
        collection_permalink (str): The permalink of this archive (e.g. handle)
        base_url (str): The base URL of the IIIF manifests and collections
    """

    fonds = parse_ead(ead_file_path)

    to_collection(fonds, base_url, "iiif/")


if __name__ == "__main__":
    main(
        ead_file_path="data/1.04.02.xml",
        base_url="https://globalise-huygens.github.io/iiif-manifests/",
    )
