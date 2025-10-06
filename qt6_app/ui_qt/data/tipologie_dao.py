-- Tipologie di esempio
INSERT INTO tipologie (nome, categoria, materiale, rif, extra, attiva, comp) VALUES
('Telaio 70x30 Alluminio', 'Telaio', 'Alluminio', 'T70x30', 'Profilo standard', 1, 2),
('Anta 60x40 PVC',        'Anta',   'PVC',       'A60x40', 'Serie termica', 1, 3),
('Traverso 45x20 Acciaio','Traverso','Acciaio',  'TR45x20','Strutturale',  1, 1);

-- Commessa demo
INSERT INTO commesse (cliente, note) VALUES ('ACME S.p.A.', 'Commessa demo');

-- Righe commessa: associazione a tipologie e tagli richiesti
INSERT INTO commessa_items (commessa_id, tipologia_id, len_mm, qty) VALUES
(1, 1, 500.0, 4),
(1, 2, 750.0, 2),
(1, 3, 620.0, 3);

-- Stock barre di esempio (per futuri test ILP)
INSERT INTO stock_bars (material, length_mm, available_qty) VALUES
('Alluminio', 6000.0, 10),
('PVC',       6000.0,  8),
('Acciaio',   7000.0,  6);
