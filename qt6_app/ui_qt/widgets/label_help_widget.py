"""
Help widget with tips and guides for the label editor.
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser, QTabWidget
from PySide6.QtCore import Qt


class LabelHelpWidget(QWidget):
    """Integrated help system for label editor."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
    
    def _build(self):
        """Build the help widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("❓ Aiuto")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)
        
        # Tab widget for different help sections
        tabs = QTabWidget()
        
        # Quick Start tab
        quick_start = self._create_quick_start()
        tabs.addTab(quick_start, "🚀 Inizio Rapido")
        
        # Tips tab
        tips = self._create_tips()
        tabs.addTab(tips, "💡 Suggerimenti")
        
        # FAQ tab
        faq = self._create_faq()
        tabs.addTab(faq, "❓ FAQ")
        
        layout.addWidget(tabs)
        
        self.setMaximumWidth(300)
        self.setStyleSheet("""
            QWidget {
                background-color: #f9f9f9;
            }
        """)
    
    def _create_quick_start(self) -> QWidget:
        """Create quick start guide."""
        widget = QTextBrowser()
        widget.setOpenExternalLinks(True)
        
        html = """
        <html>
        <body style="font-family: Arial; font-size: 12px; padding: 10px;">
            <h2>Inizio Rapido</h2>
            
            <h3>1. Aggiungi Elementi</h3>
            <p>Clicca sui pulsanti nella barra laterale sinistra per aggiungere elementi all'etichetta.</p>
            
            <h3>2. Posiziona e Ridimensiona</h3>
            <ul>
                <li>Trascina gli elementi per spostarli</li>
                <li>Usa i quadratini blu per ridimensionare</li>
                <li>La griglia aiuta l'allineamento</li>
            </ul>
            
            <h3>3. Modifica Proprietà</h3>
            <p>Seleziona un elemento e usa il pannello destro per modificarne le proprietà (testo, font, colori, ecc.).</p>
            
            <h3>4. Salva Template</h3>
            <p>Usa il pulsante "Salva Template" per salvare il tuo layout per usi futuri.</p>
            
            <h3>5. Stampa di Test</h3>
            <p>Clicca "Stampa Test" per verificare il risultato prima della stampa finale.</p>
        </body>
        </html>
        """
        widget.setHtml(html)
        return widget
    
    def _create_tips(self) -> QWidget:
        """Create tips section."""
        widget = QTextBrowser()
        widget.setOpenExternalLinks(True)
        
        html = """
        <html>
        <body style="font-family: Arial; font-size: 12px; padding: 10px;">
            <h2>Suggerimenti Utili</h2>
            
            <h3>⌨️ Scorciatoie da Tastiera</h3>
            <ul>
                <li><b>Ctrl+Z</b> - Annulla ultima modifica</li>
                <li><b>Ctrl+Y</b> - Ripristina modifica</li>
                <li><b>Ctrl+D</b> - Duplica elemento selezionato</li>
                <li><b>Canc</b> - Elimina elemento selezionato</li>
                <li><b>Frecce</b> - Sposta elemento (1mm)</li>
                <li><b>Shift+Frecce</b> - Sposta elemento (10mm)</li>
            </ul>
            
            <h3>📐 Allineamento</h3>
            <ul>
                <li>Attiva la griglia per un allineamento preciso</li>
                <li>Le guide di allineamento appaiono automaticamente</li>
                <li>Gli elementi si "agganciano" alla griglia</li>
            </ul>
            
            <h3>🎨 Progettazione</h3>
            <ul>
                <li>Usa font ≥ 8pt per garantire leggibilità</li>
                <li>Mantieni i margini di 5mm dai bordi</li>
                <li>Testa sempre prima della stampa finale</li>
                <li>Usa template predefiniti come punto di partenza</li>
            </ul>
            
            <h3>🔢 Campi Dinamici</h3>
            <p>I campi dinamici vengono riempiti automaticamente con i dati del pezzo:</p>
            <ul>
                <li><b>length</b> - Lunghezza pezzo</li>
                <li><b>profile_name</b> - Nome profilo</li>
                <li><b>order_id</b> - ID ordine</li>
                <li><b>piece_id</b> - ID pezzo</li>
                <li>...e molti altri</li>
            </ul>
        </body>
        </html>
        """
        widget.setHtml(html)
        return widget
    
    def _create_faq(self) -> QWidget:
        """Create FAQ section."""
        widget = QTextBrowser()
        widget.setOpenExternalLinks(True)
        
        html = """
        <html>
        <body style="font-family: Arial; font-size: 12px; padding: 10px;">
            <h2>Domande Frequenti</h2>
            
            <h3>❓ Come aggiungo un logo?</h3>
            <p>Aggiungi un elemento "Immagine" e specifica il percorso del file nel pannello proprietà.</p>
            
            <h3>❓ Come creo un barcode?</h3>
            <p>Aggiungi un elemento "Barcode", seleziona il tipo (Code128, QR, ecc.) e la sorgente dati.</p>
            
            <h3>❓ L'elemento esce dall'etichetta</h3>
            <p>Controlla la posizione e dimensione nel pannello proprietà. Gli elementi devono stare dentro i margini.</p>
            
            <h3>❓ Come duplico un elemento?</h3>
            <p>Seleziona l'elemento e premi Ctrl+D oppure usa il menu contestuale (tasto destro).</p>
            
            <h3>❓ Il font è troppo piccolo</h3>
            <p>Aumenta la dimensione del font nel pannello proprietà. Si consiglia almeno 8pt per la leggibilità.</p>
            
            <h3>❓ Come testo la stampa?</h3>
            <p>Usa il pulsante "Stampa Test" per stampare un'etichetta di prova con dati fittizi.</p>
            
            <h3>❓ Posso condividere i template?</h3>
            <p>Sì! Usa "Esporta Template" per salvare un file JSON che puoi condividere con altri.</p>
            
            <h3>❓ Come ripristino un template predefinito?</h3>
            <p>I template predefiniti (Standard, Minimal, ecc.) non possono essere eliminati e sono sempre disponibili.</p>
        </body>
        </html>
        """
        widget.setHtml(html)
        return widget
