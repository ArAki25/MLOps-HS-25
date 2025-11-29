"""
Datenmodelle für Simap.ch KI-Assistent
"""


class User:
    """Benutzer-Model"""

    def __init__(self, email, password, firma, name):
        self.email = email
        self.password = password  # In Produktion: gehashed!
        self.firma = firma
        self.name = name

    def to_dict(self):
        """Konvertiere zu Dictionary"""
        return {
            'email': self.email,
            'firma': self.firma,
            'name': self.name
        }


class Ausschreibung:
    """Ausschreibungs-Model"""

    def __init__(self, id, titel, unternehmen, wert, deadline, status,
                 relevanz, kategorie, beschreibung):
        self.id = id
        self.titel = titel
        self.unternehmen = unternehmen
        self.wert = wert
        self.deadline = deadline
        self.status = status  # 'neu', 'laufend', 'abgeschlossen'
        self.relevanz = relevanz  # 0-100
        self.kategorie = kategorie
        self.beschreibung = beschreibung

    def to_dict(self):
        """Konvertiere zu Dictionary für JSON"""
        return {
            'id': self.id,
            'titel': self.titel,
            'unternehmen': self.unternehmen,
            'wert': self.wert,
            'deadline': self.deadline,
            'status': self.status,
            'relevanz': self.relevanz,
            'kategorie': self.kategorie,
            'beschreibung': self.beschreibung
        }


def get_statistics(ausschreibungen):
    """
    Berechne Statistiken aus Ausschreibungsliste

    Args:
        ausschreibungen: Liste von Ausschreibung-Objekten

    Returns:
        Dictionary mit Statistiken
    """
    neue = len([a for a in ausschreibungen if a.status == 'neu'])
    laufend = len([a for a in ausschreibungen if a.status == 'laufend'])
    abgeschlossen = len([a for a in ausschreibungen if a.status == 'abgeschlossen'])

    return {
        'neue': neue,
        'laufend': laufend,
        'abgeschlossen': abgeschlossen,
        'volumen': '2.4 Mio CHF'  # Kann später dynamisch berechnet werden
    }