from app.artisans.site_finder import _extract_contact, _response_data, _url_candidate


def test_rejette_annuaires_et_reseaux_sociaux():
    assert _url_candidate("https://annuaire-entreprises.data.gouv.fr/entreprise/123") is None
    assert _url_candidate("https://www.facebook.com/artisan") is None


def test_normalise_un_site_entreprise():
    assert _url_candidate("artisan-exemple.fr/contact") == "https://artisan-exemple.fr/contact"


def test_extrait_references_et_texte():
    response = {
        "outputs": [{
            "type": "message.output",
            "content": [
                {"type": "tool_reference", "url": "https://artisan-exemple.fr"},
                {"type": "text", "text": (
                    "SITE_OFFICIEL: https://artisan-exemple.fr\n"
                    "TELEPHONE: 01 02 03 04 05\n"
                    "EMAIL: contact@artisan-exemple.fr"
                )},
            ],
        }],
    }
    urls, texts = _response_data(response)
    assert urls == ["https://artisan-exemple.fr"]
    assert "SITE_OFFICIEL" in texts[0]
    contact = _extract_contact(response)
    assert contact == {
        "site_officiel": "https://artisan-exemple.fr",
        "telephone": "01 02 03 04 05",
        "email": "contact@artisan-exemple.fr",
    }
