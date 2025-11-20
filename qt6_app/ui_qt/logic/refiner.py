"""
Modulo per il raffinamento del piano di taglio
File: qt6_app/ui_qt/logic/refiner.py
Date: 2025-11-20
Author: house79-gex
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def refine_plan(plan: Dict, kerf: float = 3.0, ripasso: float = 5.0, recupero: bool = True) -> Dict:
    """
    Raffina il piano di taglio applicando parametri di taglio reali
    
    Args:
        plan: Piano di taglio grezzo
        kerf: Larghezza della lama in mm
        ripasso: Lunghezza di ripasso per garantire il taglio completo
        recupero: Se True, tenta di recuperare gli sfridi utilizzabili
        
    Returns:
        Piano raffinato con parametri di taglio applicati
    """
    if not plan or 'bars' not in plan:
        return plan
        
    refined_plan = plan.copy()
    refined_bars = []
    total_waste = 0
    recoverable_pieces = []
    
    for bar in plan.get('bars', []):
        refined_bar = refine_bar(bar, kerf, ripasso)
        
        # Calcola lo sfrido
        bar_length = refined_bar.get('length', 0)
        used_length = calculate_used_length(refined_bar, kerf)
        waste = bar_length - used_length
        
        refined_bar['waste'] = waste
        refined_bar['used_length'] = used_length
        refined_bar['efficiency'] = (used_length / bar_length * 100) if bar_length > 0 else 0
        
        # Se il recupero è abilitato e lo sfrido è significativo
        if recupero and waste > 100:  # Minimo 100mm per essere recuperabile
            recoverable_pieces.append({
                'bar_id': refined_bar.get('id'),
                'length': waste - kerf,  # Considera il kerf per il taglio di separazione
                'type': 'scrap'
            })
            
        refined_bars.append(refined_bar)
        total_waste += waste
        
    refined_plan['bars'] = refined_bars
    refined_plan['total_waste'] = total_waste
    refined_plan['recoverable_pieces'] = recoverable_pieces
    
    # Aggiungi statistiche di raffinamento
    refined_plan['refinement_params'] = {
        'kerf': kerf,
        'ripasso': ripasso,
        'recupero': recupero
    }
    
    logger.info(f"Piano raffinato: {len(refined_bars)} barre, sfrido totale: {total_waste:.1f}mm")
    
    return refined_plan


def refine_bar(bar: Dict, kerf: float, ripasso: float) -> Dict:
    """
    Raffina una singola barra applicando kerf e ripasso
    
    Args:
        bar: Dati della barra
        kerf: Larghezza della lama
        ripasso: Lunghezza di ripasso
        
    Returns:
        Barra raffinata
    """
    refined_bar = bar.copy()
    refined_jobs = []
    
    for job in bar.get('jobs', []):
        refined_job = job.copy()
        
        # Applica il ripasso alla lunghezza
        original_length = refined_job.get('length', 0)
        refined_job['original_length'] = original_length
        refined_job['actual_length'] = original_length + ripasso
        
        # Aggiungi informazioni sul kerf
        refined_job['kerf'] = kerf
        refined_job['ripasso'] = ripasso
        
        # Calcola posizioni di taglio considerando il kerf
        refined_job['cut_compensation'] = calculate_cut_compensation(
            refined_job.get('angle_sx', 90),
            refined_job.get('angle_dx', 90),
            kerf
        )
        
        refined_jobs.append(refined_job)
        
    refined_bar['jobs'] = refined_jobs
    return refined_bar


def calculate_used_length(bar: Dict, kerf: float) -> float:
    """
    Calcola la lunghezza effettivamente utilizzata in una barra
    
    Args:
        bar: Dati della barra
        kerf: Larghezza della lama
        
    Returns:
        Lunghezza utilizzata in mm
    """
    jobs = bar.get('jobs', [])
    if not jobs:
        return 0
        
    total_length = 0
    
    for i, job in enumerate(jobs):
        # Lunghezza del pezzo
        total_length += job.get('actual_length', job.get('length', 0))
        
        # Aggiungi il kerf tra i pezzi (non dopo l'ultimo)
        if i < len(jobs) - 1:
            total_length += kerf
            
    return total_length


def calculate_cut_compensation(angle_sx: float, angle_dx: float, kerf: float) -> Dict:
    """
    Calcola la compensazione per tagli angolati
    
    Args:
        angle_sx: Angolo sinistro in gradi
        angle_dx: Angolo destro in gradi
        kerf: Larghezza della lama
        
    Returns:
        Dizionario con compensazioni calcolate
    """
    import math
    
    compensation = {
        'sx': 0,
        'dx': 0
    }
    
    # Per tagli non perpendicolari, calcola la compensazione
    if angle_sx != 90:
        # Compensazione per angolo sinistro
        rad = math.radians(angle_sx)
        compensation['sx'] = kerf / (2 * math.sin(rad)) if math.sin(rad) != 0 else 0
        
    if angle_dx != 90:
        # Compensazione per angolo destro
        rad = math.radians(angle_dx)
        compensation['dx'] = kerf / (2 * math.sin(rad)) if math.sin(rad) != 0 else 0
        
    return compensation


def optimize_for_material(plan: Dict, material_type: str = 'aluminum') -> Dict:
    """
    Ottimizza il piano per il tipo di materiale specifico
    
    Args:
        plan: Piano di taglio
        material_type: Tipo di materiale (aluminum, steel, wood, etc.)
        
    Returns:
        Piano ottimizzato per il materiale
    """
    material_params = {
        'aluminum': {
            'cutting_speed': 100,
            'feed_rate': 50,
            'coolant': True,
            'blade_type': 'carbide'
        },
        'steel': {
            'cutting_speed': 50,
            'feed_rate': 25,
            'coolant': True,
            'blade_type': 'hss'
        },
        'wood': {
            'cutting_speed': 150,
            'feed_rate': 75,
            'coolant': False,
            'blade_type': 'wood'
        }
    }
    
    params = material_params.get(material_type, material_params['aluminum'])
    
    optimized_plan = plan.copy()
    optimized_plan['material'] = material_type
    optimized_plan['cutting_params'] = params
    
    # Calcola tempi di taglio stimati
    total_time = 0
    for bar in optimized_plan.get('bars', []):
        for job in bar.get('jobs', []):
            length = job.get('length', 0)
            # Tempo = lunghezza / velocità di avanzamento
            cut_time = (length / params['feed_rate']) * 60  # in secondi
            job['estimated_time'] = cut_time
            total_time += cut_time
            
    optimized_plan['total_estimated_time'] = total_time
    
    return optimized_plan


def group_by_angle(plan: Dict) -> Dict:
    """
    Raggruppa i tagli per angolo per minimizzare i cambi testa
    
    Args:
        plan: Piano di taglio
        
    Returns:
        Piano con tagli raggruppati per angolo
    """
    grouped_plan = plan.copy()
    
    for bar in grouped_plan.get('bars', []):
        jobs = bar.get('jobs', [])
        
        # Raggruppa per combinazione di angoli
        angle_groups = {}
        for job in jobs:
            angle_key = (job.get('angle_sx', 90), job.get('angle_dx', 90))
            if angle_key not in angle_groups:
                angle_groups[angle_key] = []
            angle_groups[angle_key].append(job)
            
        # Riordina i jobs raggruppati
        grouped_jobs = []
        for angle_key in sorted(angle_groups.keys()):
            grouped_jobs.extend(angle_groups[angle_key])
            
        bar['jobs'] = grouped_jobs
        bar['angle_changes'] = len(angle_groups) - 1
        
    return grouped_plan


def add_setup_operations(plan: Dict) -> Dict:
    """
    Aggiunge operazioni di setup tra i tagli
    
    Args:
        plan: Piano di taglio
        
    Returns:
        Piano con operazioni di setup
    """
    setup_plan = plan.copy()
    
    for bar in setup_plan.get('bars', []):
        jobs_with_setup = []
        last_angles = (90, 90)
        
        for job in bar.get('jobs', []):
            current_angles = (job.get('angle_sx', 90), job.get('angle_dx', 90))
            
            # Se gli angoli sono diversi, aggiungi operazione di setup
            if current_angles != last_angles:
                setup_op = {
                    'type': 'setup',
                    'operation': 'angle_change',
                    'from_angles': last_angles,
                    'to_angles': current_angles,
                    'estimated_time': 30  # secondi
                }
                jobs_with_setup.append(setup_op)
                
            jobs_with_setup.append(job)
            last_angles = current_angles
            
        bar['jobs_with_setup'] = jobs_with_setup
        
    return setup_plan


def validate_plan(plan: Dict) -> tuple[bool, List[str]]:
    """
    Valida un piano di taglio
    
    Args:
        plan: Piano da validare
        
    Returns:
        Tupla (valido, lista_errori)
    """
    errors = []
    
    if not plan:
        errors.append("Piano vuoto")
        return False, errors
        
    if 'bars' not in plan:
        errors.append("Piano senza barre")
        return False, errors
        
    bars = plan.get('bars', [])
    
    if not bars:
        errors.append("Nessuna barra nel piano")
        return False, errors
        
    for i, bar in enumerate(bars):
        # Controlla che la barra abbia una lunghezza
        if 'length' not in bar or bar['length'] <= 0:
            errors.append(f"Barra {i+1}: lunghezza non valida")
            
        # Controlla i jobs
        jobs = bar.get('jobs', [])
        if not jobs:
            errors.append(f"Barra {i+1}: nessun taglio definito")
            
        total_length = 0
        for j, job in enumerate(jobs):
            if 'length' not in job or job['length'] <= 0:
                errors.append(f"Barra {i+1}, Taglio {j+1}: lunghezza non valida")
                
            total_length += job.get('length', 0)
            
            # Controlla angoli
            angle_sx = job.get('angle_sx', 90)
            angle_dx = job.get('angle_dx', 90)
            
            if not (0 < angle_sx <= 180):
                errors.append(f"Barra {i+1}, Taglio {j+1}: angolo sinistro non valido")
                
            if not (0 < angle_dx <= 180):
                errors.append(f"Barra {i+1}, Taglio {j+1}: angolo destro non valido")
                
        # Controlla che i tagli non superino la lunghezza della barra
        if total_length > bar.get('length', 0):
            errors.append(f"Barra {i+1}: lunghezza tagli ({total_length}) supera lunghezza barra ({bar.get('length', 0)})")
            
    return len(errors) == 0, errors


def merge_small_scraps(plan: Dict, min_length: float = 100) -> Dict:
    """
    Unisce gli sfridi piccoli per creare pezzi recuperabili
    
    Args:
        plan: Piano di taglio
        min_length: Lunghezza minima per considerare uno sfrido recuperabile
        
    Returns:
        Piano con sfridi ottimizzati
    """
    merged_plan = plan.copy()
    scraps = []
    
    # Raccogli tutti gli sfridi
    for bar in merged_plan.get('bars', []):
        waste = bar.get('waste', 0)
        if waste > 0:
            scraps.append({
                'bar_id': bar.get('id'),
                'length': waste
            })
            
    # Ordina per lunghezza decrescente
    scraps.sort(key=lambda x: x['length'], reverse=True)
    
    # Unisci sfridi piccoli
    merged_scraps = []
    current_group = []
    current_total = 0
    
    for scrap in scraps:
        if scrap['length'] >= min_length:
            # Sfrido già utilizzabile
            merged_scraps.append(scrap)
        else:
            # Aggiungi al gruppo corrente
            current_group.append(scrap)
            current_total += scrap['length']
            
            if current_total >= min_length:
                # Gruppo utilizzabile
                merged_scraps.append({
                    'bar_ids': [s['bar_id'] for s in current_group],
                    'length': current_total,
                    'type': 'merged_scrap'
                })
                current_group = []
                current_total = 0
                
    merged_plan['optimized_scraps'] = merged_scraps
    
    return merged_plan


# Esporta tutte le funzioni pubbliche
__all__ = [
    'refine_plan',
    'refine_bar',
    'calculate_used_length',
    'calculate_cut_compensation',
    'optimize_for_material',
    'group_by_angle',
    'add_setup_operations',
    'validate_plan',
    'merge_small_scraps'
]
