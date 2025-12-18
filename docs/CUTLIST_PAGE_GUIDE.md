# Cutlist Page - Feature Documentation

## Overview

The Cutlist Page provides a comprehensive interface for managing cutting lists with import/export capabilities, manual editing, optimization, and project management.

## Accessing the Feature

1. Launch the Blitz application
2. From the home page, click on **"Cutlist Manager"** button
3. The Cutlist Page will open with all features available

## Main Interface Components

### 1. Import Section
Located at the top of the page with buttons for:
- **CSV Import** - Import from comma-separated values files
- **Excel Import** - Import from .xlsx files  
- **TXT Import** - Import from plain text files (one length per line)
- **JSON Import** - Import complete projects with settings

### 2. Cutlist Editor Table
The main editing area featuring:
- **Columns**: Row #, Length (mm), Quantity, Label
- **Row numbers**: Automatically numbered (non-editable)
- **Editable cells**: Click to edit length, quantity, or label
- **Visual validation**: 
  - Red background = Error (length ≤ 0, quantity < 1)
  - Orange background = Warning (length > stock length)
  - White background = Valid

### 3. Table Controls
Below the table:
- **+ Aggiungi Riga** - Add a new row
- **− Rimuovi Selezionati** - Remove selected rows
- **📋 Duplica** - Duplicate selected row
- **🗑️ Cancella Tutto** - Clear all rows (with confirmation)

### 4. Totals Display
Shows real-time totals:
- Total number of pieces
- Total linear meters

Example: `Totale: 10 pezzi | 12.64 metri lineari`

### 5. Optimization Parameters
Configure optimization settings:
- **Lunghezza stock**: Stock bar length in mm (default: 6500mm)
- **Kerf lama**: Blade kerf in mm (default: 3mm)

### 6. Action Buttons
Main actions:
- **⚙️ OTTIMIZZA** - Run optimization on current cutlist
- **💾 Salva Progetto** - Save current work as a project

### 7. Results Display
After optimization, shows:
- Success message
- Statistics:
  - Bars used
  - Total waste (mm)
  - Efficiency (%)
- Cutting plan:
  - Detailed breakdown per bar
  - Pieces in each bar with labels
  - Waste per bar
- Export buttons:
  - **📄 Esporta PDF** - Export visual cut plan
  - **📊 Esporta Excel** - Export cutlist + results

### 8. Recent Projects
Shows last 5 saved projects with:
- Project name (📁 icon)
- Number of pieces and total length
- Last modified date/time
- **📂 Carica** button - Load project
- **🗑️** button - Delete project

## File Formats

### CSV Format
```csv
length,quantity,label
1250,5,Fermavetro A
800,3,Vetro Standard
1420,2,Astina Lunga
```

### TXT Format
```
1250
800
800
1420
1250
```
(One length per line, quantity defaults to 1)

### JSON/Project Format (.blz)
```json
{
  "project_name": "Progetto Fermavetri",
  "stock_length": 6500,
  "kerf": 3,
  "pieces": [
    {"length": 1250, "quantity": 5, "label": "Fermavetro A"},
    {"length": 800, "quantity": 3, "label": "Vetro Standard"}
  ],
  "created_at": "2025-12-18T10:30:00Z",
  "modified_at": "2025-12-18T15:45:00Z",
  "notes": ""
}
```

## Keyboard Shortcuts

- **Delete** - Remove selected rows
- **Ctrl+D** - Duplicate selected row

## Workflow Examples

### Example 1: Import and Optimize
1. Click **📊 Excel** to import a cutlist from Excel
2. Review the imported data in the table
3. Adjust **Lunghezza stock** and **Kerf** if needed
4. Click **⚙️ OTTIMIZZA**
5. Review results and export to PDF or Excel

### Example 2: Manual Entry and Save
1. Click **+ Aggiungi Riga** to add pieces
2. Fill in Length, Quantity, and Label for each piece
3. Click **⚙️ OTTIMIZZA** to run optimization
4. Click **💾 Salva Progetto** to save for later
5. Enter a project name (e.g., "Commessa #123")

### Example 3: Load and Modify Existing Project
1. Find project in **Progetti Recenti** section
2. Click **📂 Carica** to load it
3. Make modifications to the cutlist
4. Click **⚙️ OTTIMIZZA** to recalculate
5. Click **💾 Salva Progetto** to update (same name)

## Validation Rules

1. **Length**: Must be > 0 and ideally < stock_length
2. **Quantity**: Must be ≥ 1
3. **Label**: Optional, max 50 characters recommended
4. **Empty rows**: Ignored during optimization

## Tips & Best Practices

1. **Import large lists**: Use CSV or Excel import for lists with many pieces
2. **Use labels**: Add descriptive labels for easier identification in cut plans
3. **Save frequently**: Save projects before optimizing to preserve work
4. **Check validation**: Red/orange cells indicate issues that should be fixed
5. **Stock length**: Set stock length before importing to see warnings early
6. **Export results**: Save PDF cut plans for workshop use

## Troubleshooting

**Problem**: Import fails with "Error importing Excel"
**Solution**: Ensure Excel file has data in columns A (length), B (quantity), C (label)

**Problem**: Optimization produces many bars
**Solution**: Check stock length is appropriate for piece lengths

**Problem**: Cannot save project
**Solution**: Ensure there's at least one valid piece in the table

**Problem**: Recent projects list is empty
**Solution**: Save a project first - it will appear in the list

## Technical Notes

- Projects are saved in: `~/blitz/projects/`
- Project files use `.blz` extension (JSON format)
- PDF exports use standard A4 page size
- Excel exports include two sheets: Cutlist and Optimization Results
- Optimization uses ILP solver (same as Automatico page)

## Future Enhancements

Planned features for future versions:
- Statistics dashboard
- Batch optimization
- Email export
- Cloud sync
- Mobile companion app
