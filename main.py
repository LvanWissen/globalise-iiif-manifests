import os
from dataclasses import dataclass, field

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
    date: str
    hasPart: list
    uri: str = field(default_factory=str)


@dataclass
class File:
    code: str
    title: str
    uri: str
    date: str
    metsid: str
    hasPart: list


@dataclass
class Document:
    code: str
    title: str
    uri: str
    date: str


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

    collection = iiif_prezi3.Collection(id=collection_id, label=f"{i.code} - {i.title}")

    metadata = [
        iiif_prezi3.KeyValueString(
            label="Identifier",
            value={"en": [i.code]},
        ),
        iiif_prezi3.KeyValueString(
            label="Title",
            value={"en": [i.title]},
        ),
    ]

    if i.uri:
        metadata.append(
            iiif_prezi3.KeyValueString(
                label="Permalink",
                value={"en": [f'<a href="{i.uri}">{i.uri}</a>']},
            )
        )

    for c in i.hasPart:
        if isinstance(c, Series):
            collection.add_item(
                to_collection(
                    c,
                    base_url,
                    prefix=collection_filename.replace(".json", "/"),
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

    with open(collection_filename, "w") as outfile:
        outfile.write(collection.json(indent=4))

    return collection


def to_manifest(
    i,
    base_url,
    prefix="",
    license_uri="https://creativecommons.org/publicdomain/mark/1.0/",
    language="en",
    fetch_from_url=False,
):
    manifest_filename = f"{prefix}{i.code}.json"
    manifest_filename = manifest_filename.replace(" ", "+")
    manifest_id = base_url + manifest_filename

    os.makedirs(os.path.dirname(manifest_filename), exist_ok=True)

    iiif_prezi3.config.configs["helpers.auto_fields.AutoLang"].auto_lang = language

    manifest = iiif_prezi3.Manifest(
        id=manifest_id,
        label=f"{i.code} - {i.title}",
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

    for n, (file_name, iiif_service_info) in enumerate(scans, 1):
        if fetch_from_url:
            manifest.make_canvas_from_iiif(
                url=iiif_service_info,
                id=f"{manifest_id}/canvas/p{n}",
                label=file_name,
                anno_id=f"{manifest_id}/canvas/p{n}/anno",
                anno_page_id=f"{manifest_id}/canvas/p{n}/annotationpage",
            )
        else:
            canvas_id = f"{manifest_id}/canvas/p{n}"

            service_id = iiif_service_info.replace("/info.json", "")

            anno_id = f"{manifest_id}/canvas/p{n}/anno"
            anno_page_id = f"{manifest_id}/canvas/p{n}/annotationpage"

            service = iiif_prezi3.ServiceItem1(
                id=service_id,
                profile="http://iiif.io/api/image/2/level1.json",
                type="ImageService2",
            )

            body_id = f"{service_id}/full/full/0/default.jpg"
            body = iiif_prezi3.ResourceItem(
                id=body_id,
                type="Image",
                service=[service],
                format="image/jpeg",
                height=100,  # mock value for now
                width=100,  # mock value for now
            )

            canvas = iiif_prezi3.Canvas(
                id=canvas_id,
                label=file_name,
                height=100,  # mock value for now
                width=100,  # mock value for now
            )
            annotation = iiif_prezi3.Annotation(
                id=anno_id,
                motivation="painting",
                body=body,
                target=canvas.id,
            )

            annotationPage = iiif_prezi3.AnnotationPage(id=anno_page_id)
            annotationPage.add_item(annotation)

            canvas.add_item(annotationPage)

            manifest.add_item(canvas)

    with open(manifest_filename, "w") as outfile:
        outfile.write(manifest.json(indent=4))

    return manifest


def get_scans(metsid, cache_path="data/gaf/"):
    NS = {"mets": "http://www.loc.gov/METS/"}

    scans = []

    if metsid:
        url = "https://service.archief.nl/gaf/api/mets/v1/" + metsid

        if cache_path and metsid + ".xml" in os.listdir(cache_path):
            print(f"Fetching {url} from cache")
            mets = ET.parse(os.path.join(cache_path, metsid + ".xml"))
        else:
            print("Fetching", url)
            xml = requests.get(url).text
            mets = ET.fromstring(bytes(xml, encoding="utf-8"))

            if cache_path:
                with open(os.path.join(cache_path, metsid + ".xml"), "w") as outfile:
                    outfile.write(xml)

        for file_el in mets.findall(
            "mets:fileSec/mets:fileGrp[@USE='DISPLAY']/mets:file",
            namespaces=NS,
        ):
            file_id = file_el.attrib["ID"][:-3]  # without IIP
            service_info_url = file_el.find(
                "./mets:FLocat[@LOCTYPE='URL']",
                namespaces=NS,
            ).attrib["{http://www.w3.org/1999/xlink}href"]

            service_info_url = service_info_url.replace("/iip/", "/iipsrv?IIIF=/")

            file_name = (
                mets.find(
                    "mets:structMap/mets:div/mets:div[@ID='" + file_id + "']",
                    namespaces=NS,
                )
                .attrib["LABEL"]
                .split("/")[-1]
            )

            scans.append((file_name, service_info_url))

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
    series_code_el = series_el.find("did/unitid[@type='series_code']")
    series_title = "".join(series_el.find("did/unittitle").itertext()).strip()
    if series_code_el is not None:
        series_code = series_code_el.text
        series_code = series_code.replace("/", "")
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

        if i:
            s.hasPart.append(i)

    return s


def get_filegrp(filegrp_el):
    filegrp_code = filegrp_el.find("did/unitid").text

    # Title
    filegrp_title = "".join(filegrp_el.find("did/unittitle").itertext()).strip()
    while "  " in filegrp_title:  # double space
        filegrp_title = filegrp_title.replace("  ", " ")

    # Date
    date_el = filegrp_el.find("did/unitdate")
    if date_el is not None:
        date = date_el.attrib.get("normal", date_el.attrib.get("text"))
    else:
        date = ""

    filegrp = FileGroup(
        code=filegrp_code,
        title=filegrp_title,
        date=date,
        hasPart=[],
    )

    file_els = filegrp_el.findall("c[@level='file']")
    for file_el in file_els:
        f = get_file(file_el)

        if f:
            filegrp.hasPart.append(f)

    return filegrp


def get_file(file_el):
    did = file_el.find("did")

    # Inventory number
    inventorynumber_el = did.find("unitid[@identifier]")
    if inventorynumber_el is not None:
        inventorynumber = inventorynumber_el.text
    else:
        return None

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
        hasPart=[],
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

    to_collection(fonds, base_url)


if __name__ == "__main__":
    main(
        ead_file_path="data/1.04.02.xml",
        base_url="https://globalise-huygens.github.io/iiif-manifests/",
    )
