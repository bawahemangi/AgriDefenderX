import os
import polib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOCALE_DIR = BASE_DIR / "locale"

TRANSLATIONS = {
    "mr": {
        "Crop Health System": "पीक आरोग्य प्रणाली",
        "Govt. of Maharashtra — MSInS": "महाराष्ट्र शासन — MSInS",
        "Scan Crop": "पीक स्कॅन करा",
        "Home": "मुख्यपृष्ठ",
        "Dashboard": "डॅशबोर्ड",
        "Admin": "अ‍ॅडमिन",
        "Log out": "लॉग आउट करा",
        "Log in": "लॉग इन करा",
        "Register": "नोंदणी करा",
        "Scan": "स्कॅन",
        "Problem Statement 26131 — Early detection & management of crop diseases and pest infestations · Government of Maharashtra": "समस्या विधान २६१३१ — पीक रोग आणि कीड प्रादुर्भाव लवकर ओळखणे · महाराष्ट्र शासन",
        "Language changed": "भाषा बदलली",
        "Scan Your Crop": "तुमचे पीक स्कॅन करा",
        "Take a photo of your crop leaf — no account needed. Get an instant AI-powered disease diagnosis and treatment advice.": "तुमच्या पिकाच्या पानाचा फोटो काढा - खात्याची गरज नाही. त्वरित AI-आधारित रोगाचे निदान आणि उपचाराचा सल्ला मिळवा.",
        "Scan freely — no login needed!": "मोफत स्कॅन करा - लॉग इनची गरज नाही!",
        "Create a free account to save scan history and receive personalised Marathi/Hindi advisories.": "तुमचा स्कॅन इतिहास जतन करण्यासाठी आणि वैयक्तिकृत मराठी सल्ला मिळवण्यासाठी मोफत खाते तयार करा.",
        "Advisory Language": "सल्ल्याची भाषा",
        "Upload or Capture Leaf Photo": "पानाचा फोटो अपलोड करा किंवा काढा",
        "Tap to upload or drag & drop": "अपलोड करण्यासाठी टॅप करा किंवा ड्रॉप करा",
        "Supports JPG, PNG, WEBP — clear photo of a single leaf works best": "JPG, PNG, WEBP समर्थित — एका पानाचा स्पष्ट फोटो सर्वोत्तम काम करतो",
        "Camera / Gallery": "कॅमेरा / गॅलरी",
        "Describe crop": "पिकाचे वर्णन करा",
        "Describe the Problem": "समस्येचे वर्णन करा",
        "optional": "ऐच्छिक",
        'e.g. "Yellow spots on tomato leaves, started 3 days ago"': 'उदा. "टोमॅटोच्या पानांवर पिवळे डाग, ३ दिवसांपूर्वी सुरू झाले"',
        "Press the 🎙 button above to speak, or type directly here.": "बोलण्यासाठी वरील 🎙 बटण दाबा किंवा थेट येथे टाइप करा.",
        "Detected": "आढळले",
        "Analysis confidence": "विश्लेषण आत्मविश्वास",
        "Treatment Advisory": "उपचार सल्ला",
        "Listen to Advisory": "सल्ला ऐका",
        "Want to save this scan?": "हे स्कॅन जतन करायचे आहे का?",
        "Create a free account to store your history, get voice advisories in Marathi, and get flagged cases reviewed by a government expert.": "तुमचा इतिहास साठवण्यासाठी आणि सरकारी तज्ञांकडून तपासणी मिळवण्यासाठी मोफत खाते तयार करा.",
        "Create Account": "खाते तयार करा",
        "Scan Another Crop": "दुसरे पीक स्कॅन करा",
        "Add New Farm": "नवीन शेत जोडा",
        "Register a new farm to keep track of its crop health.": "पिकाच्या आरोग्यावर लक्ष ठेवण्यासाठी नवीन शेताची नोंदणी करा.",
        "Farm Name": "शेताचे नाव",
        "e.g. Tomato Field": "उदा. टोमॅटोचे शेत",
        "Area (Acres)": "क्षेत्र (एकर)",
        "District": "जिल्हा",
        "Select": "निवडा",
        "Taluka": "तालुका",
        "Village": "गाव",
        "Current Crop": "सध्याचे पीक",
        "Save Farm": "शेत जतन करा",
        "Cancel": "रद्द करा",
        "Add": "जोडा",
        "Welcome": "स्वागत आहे",
        "My Farms": "माझी शेते",
        "Acres": "एकर",
        "No farms registered.": "कोणतेही शेत नोंदणीकृत नाही.",
        "How it works": "हे कसे कार्य करते",
        "Upload a crop photo": "पिकाचा फोटो अपलोड करा",
        "AI detects diseases": "AI रोग ओळखते",
        "Risk scored via Weather & Pests": "हवामान आणि कीड द्वारे जोखीम स्कोअर",
        "Get actionable management advice": "कृतीयोग्य व्यवस्थापन सल्ला मिळवा",
        "Recent Scans": "अलीकडील स्कॅन",
        "View All": "सर्व पहा",
        "Crop": "पीक",
        "No crop scans yet": "अद्याप कोणतेही पीक स्कॅन नाही",
        "Upload a photo of your crop to check its health.": "तुमच्या पिकाचे आरोग्य तपासण्यासाठी फोटो अपलोड करा.",
        "Scan your first crop": "तुमचे पहिले पीक स्कॅन करा",
        "You don't have a farm registered yet.": "तुमच्याकडे अद्याप कोणतेही शेत नोंदणीकृत नाही.",
        "Add a farm": "शेत जोडा",
        "to get started.": "सुरू करण्यासाठी."
    },
    "hi": {
        "Crop Health System": "फसल स्वास्थ्य प्रणाली",
        "Govt. of Maharashtra — MSInS": "महाराष्ट्र सरकार — MSInS",
        "Scan Crop": "फसल स्कैन करें",
        "Home": "होम",
        "Dashboard": "डैशबोर्ड",
        "Admin": "एडमिन",
        "Log out": "लॉग आउट करें",
        "Log in": "लॉग इन करें",
        "Register": "रजिस्टर करें",
        "Scan": "स्कैन",
        "Problem Statement 26131 — Early detection & management of crop diseases and pest infestations · Government of Maharashtra": "समस्या विवरण 26131 — फसल रोगों और कीटों की प्रारंभिक पहचान · महाराष्ट्र सरकार",
        "Language changed": "भाषा बदल गई",
        "Scan Your Crop": "अपनी फसल स्कैन करें",
        "Take a photo of your crop leaf — no account needed. Get an instant AI-powered disease diagnosis and treatment advice.": "अपनी फसल के पत्ते की तस्वीर लें - खाते की आवश्यकता नहीं है। त्वरित AI-आधारित निदान प्राप्त करें।",
        "Scan freely — no login needed!": "स्वतंत्र रूप से स्कैन करें - लॉग इन की आवश्यकता नहीं!",
        "Create a free account to save scan history and receive personalised Marathi/Hindi advisories.": "अपने स्कैन इतिहास को सहेजने और व्यक्तिगत सलाह प्राप्त करने के लिए निःशुल्क खाता बनाएं।",
        "Advisory Language": "सलाह की भाषा",
        "Upload or Capture Leaf Photo": "पत्ते की फोटो अपलोड करें या खींचें",
        "Tap to upload or drag & drop": "अपलोड करने के लिए टैप करें",
        "Supports JPG, PNG, WEBP — clear photo of a single leaf works best": "JPG, PNG, WEBP समर्थित — एक पत्ते की स्पष्ट तस्वीर सबसे अच्छी काम करती है",
        "Camera / Gallery": "कैमरा / गैलरी",
        "Describe crop": "फसल का वर्णन करें",
        "Describe the Problem": "समस्या का वर्णन करें",
        "optional": "वैकल्पिक",
        'e.g. "Yellow spots on tomato leaves, started 3 days ago"': 'उदा. "टमाटर के पत्तों पर पीले धब्बे, 3 दिन पहले शुरू हुए"',
        "Press the 🎙 button above to speak, or type directly here.": "बोलने के लिए 🎙 बटन दबाएं, या सीधे यहां टाइप करें।",
        "Detected": "पता चला",
        "Analysis confidence": "विश्लेषण आत्मविश्वास",
        "Treatment Advisory": "उपचार सलाह",
        "Listen to Advisory": "सलाह सुनें",
        "Want to save this scan?": "क्या आप इस स्कैन को सहेजना चाहते हैं?",
        "Create a free account to store your history, get voice advisories in Marathi, and get flagged cases reviewed by a government expert.": "अपने इतिहास को सहेजने और सरकारी विशेषज्ञ से जांच कराने के लिए निःशुल्क खाता बनाएं।",
        "Create Account": "खाता बनाएं",
        "Scan Another Crop": "दूसरी फसल स्कैन करें",
        "Add New Farm": "नया खेत जोड़ें",
        "Register a new farm to keep track of its crop health.": "फसल के स्वास्थ्य पर नज़र रखने के लिए एक नया खेत पंजीकृत करें।",
        "Farm Name": "खेत का नाम",
        "e.g. Tomato Field": "उदा. टमाटर का खेत",
        "Area (Acres)": "क्षेत्र (एकड़)",
        "District": "ज़िला",
        "Select": "चुनें",
        "Taluka": "तालुका",
        "Village": "गाँव",
        "Current Crop": "वर्तमान फसल",
        "Save Farm": "खेत सहेजें",
        "Cancel": "रद्द करें",
        "Add": "जोड़ें",
        "Welcome": "स्वागत है",
        "My Farms": "मेरे खेत",
        "Acres": "एकड़",
        "No farms registered.": "कोई खेत पंजीकृत नहीं है।",
        "How it works": "यह कैसे काम करता है",
        "Upload a crop photo": "फसल की फोटो अपलोड करें",
        "AI detects diseases": "AI रोगों का पता लगाता है",
        "Risk scored via Weather & Pests": "मौसम और कीटों के माध्यम से जोखिम स्कोर",
        "Get actionable management advice": "कार्रवाई योग्य प्रबंधन सलाह प्राप्त करें",
        "Recent Scans": "हाल के स्कैन",
        "View All": "सभी देखें",
        "Crop": "फसल",
        "No crop scans yet": "अभी तक कोई फसल स्कैन नहीं",
        "Upload a photo of your crop to check its health.": "अपनी फसल के स्वास्थ्य की जांच के लिए फोटो अपलोड करें।",
        "Scan your first crop": "अपनी पहली फसल स्कैन करें",
        "You don't have a farm registered yet.": "आपका कोई खेत अभी तक पंजीकृत नहीं है।",
        "Add a farm": "खेत जोड़ें",
        "to get started.": "शुरू करने के लिए।"
    }
}

def main():
    for lang_code, strings in TRANSLATIONS.items():
        lang_dir = LOCALE_DIR / lang_code / "LC_MESSAGES"
        lang_dir.mkdir(parents=True, exist_ok=True)
        po_path = lang_dir / "django.po"
        mo_path = lang_dir / "django.mo"
        
        po = polib.POFile()
        po.metadata = {
            'Project-Id-Version': '1.0',
            'Report-Msgid-Bugs-To': '',
            'POT-Creation-Date': '2026-09-24 19:00+0530',
            'PO-Revision-Date': '2026-09-24 19:00+0530',
            'Last-Translator': 'Auto <auto@example.com>',
            'Language-Team': f'{lang_code} <LL@li.org>',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Transfer-Encoding': '8bit',
            'Language': lang_code,
        }
        
        for msgid, msgstr in strings.items():
            entry = polib.POEntry(msgid=msgid, msgstr=msgstr)
            po.append(entry)
            
        po.save(str(po_path))
        po.save_as_mofile(str(mo_path))
        print(f"Generated {mo_path}")

if __name__ == '__main__':
    main()
