"""Embed the edit manifest into the restored PNG as a signed C2PA Content Credential.
Signed with the c2pa-python TEST certificate: demo only, shows as untrusted in readers."""
from pathlib import Path
import c2pa
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

CERTS = Path("weights/c2pa_test/es256_certs.pem")
KEY = Path("weights/c2pa_test/es256_private.key")
TSA = "http://timestamp.digicert.com"

def embed(src_png, dst_png, manifest, title="ChronoVisage restoration"):
    certs = CERTS.read_bytes()
    key = serialization.load_pem_private_key(KEY.read_bytes(), password=None)

    def sign_cb(data: bytes) -> bytes:
        return key.sign(data, ec.ECDSA(hashes.SHA256()))

    definition = {
        "claim_generator_info": [{"name": "ChronoVisage", "version": "0.1"}],
        "format": "image/png",
        "title": title,
        "ingredients": [],
        "assertions": [
            {"label": "c2pa.actions", "data": {"actions": [{
                "action": "c2pa.created",
                "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
            }]}},
            {"label": "org.chronovisage.edit_manifest", "data": manifest},
        ],
    }
    with c2pa.Signer.from_callback(sign_cb, c2pa.C2paSigningAlg.ES256, certs.decode(), TSA) as signer:
        if hasattr(c2pa, "Context"):
            with c2pa.Context() as ctx, c2pa.Builder(definition, ctx) as builder:
                builder.sign_file(str(src_png), str(dst_png), signer)
        else:
            with c2pa.Builder(definition) as builder:
                builder.sign_file(str(src_png), str(dst_png), signer)

def read(path):
    """Return the C2PA manifest store JSON embedded in a file."""
    with open(path, "rb") as f, c2pa.Reader("image/png", f) as r:
        return r.json()
