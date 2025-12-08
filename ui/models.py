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
    """Ausschreibungs-Model für UI-Darstellung"""

    def __init__(self, id, titel, unternehmen, wert, deadline, status,
                 relevanz, kategorie, beschreibung, canton=None, 
                 publication_type=None, project_id=None):
        self.id = id
        self.titel = titel
        self.unternehmen = unternehmen
        self.wert = wert
        self.deadline = deadline
        self.status = status  # 'neu', 'laufend', 'abgeschlossen'
        self.relevanz = relevanz  # 0-100
        self.kategorie = kategorie
        self.beschreibung = beschreibung
        self.canton = canton
        self.publication_type = publication_type
        self.project_id = project_id

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
            'beschreibung': self.beschreibung,
            'canton': self.canton,
            'publication_type': self.publication_type,
            'project_id': self.project_id,
        }

    @classmethod
    def from_db_row(cls, row: dict, relevanz: int = 50):
        """
        Erstellt eine Ausschreibung aus einem Datenbank-Row.
        
        Args:
            row: Dictionary mit Datenbank-Feldern
            relevanz: KI-Relevanz-Score (0-100)
        """
        # Status basierend auf publication_type bestimmen
        pub_type = row.get('publication_type', '')
        if pub_type == 'award':
            status = 'abgeschlossen'
        elif pub_type == 'tender':
            status = 'neu'
        else:
            status = 'laufend'
        
        # Wert formatieren
        amount = row.get('estimated_amount') or row.get('award_amount')
        if amount:
            wert = f"{amount:,.0f} CHF".replace(',', "'")
        else:
            wert = "k.A."
        
        # Deadline formatieren
        deadline = row.get('submission_deadline')
        if deadline:
            if hasattr(deadline, 'strftime'):
                deadline = deadline.strftime('%d.%m.%Y')
            else:
                deadline = str(deadline)[:10]
        else:
            deadline = "k.A."
        
        return cls(
            id=hash(row.get('project_id', '')) % 100000,
            titel=row.get('title', 'Ohne Titel')[:100],
            unternehmen=row.get('contracting_authority', 'Unbekannt'),
            wert=wert,
            deadline=deadline,
            status=status,
            relevanz=relevanz,
            kategorie=row.get('order_type', 'Allgemein'),
            beschreibung=row.get('description', '')[:200] if row.get('description') else '',
            canton=row.get('canton'),
            publication_type=pub_type,
            project_id=row.get('project_id'),
        )


def get_statistics(ausschreibungen):
    """
    Berechne Statistiken aus Ausschreibungsliste

    Args:
        ausschreibungen: Liste von Ausschreibung-Objekten oder Dicts

    Returns:
        Dictionary mit Statistiken
    """
    if not ausschreibungen:
        return {
            'neue': 0,
            'laufend': 0,
            'abgeschlossen': 0,
            'volumen': '0 CHF'
        }
    
    # Support für beide Formate (Objekte und Dicts)
    def get_status(a):
        if hasattr(a, 'status'):
            return a.status
        return a.get('status', '')
    
    neue = len([a for a in ausschreibungen if get_status(a) == 'neu'])
    laufend = len([a for a in ausschreibungen if get_status(a) == 'laufend'])
    abgeschlossen = len([a for a in ausschreibungen if get_status(a) == 'abgeschlossen'])

    return {
        'neue': neue,
        'laufend': laufend,
        'abgeschlossen': abgeschlossen,
        'volumen': f"{len(ausschreibungen)} Projekte"
    }

