"""Validate the category tile separately from the model's chosen control ID."""
ACRONYMS={
    'DOCTOR':('Description/date','Origin','Characteristics','Time','Occupation','Relationships'),
    'PLACE':('Position','Location','Action','Condition','Emotions'),
}


def category_control(controls,acronym,category):
    names=ACRONYMS.get(acronym)
    if not names:raise ValueError('Unknown Spanish category acronym.')
    aliases={'description':'Description/date','date':'Description/date','emotion':'Emotions','relationship':'Relationships','characteristic':'Characteristics'}
    category=aliases.get(category.strip().casefold(),category.strip())
    indices=[i for i,name in enumerate(names) if name.casefold()==category.casefold()]
    if len(indices)!=1:raise ValueError('Use the full category name, not an ambiguous acronym letter.')
    choices=sorted((c for c in controls if c.get('answer_choice') and not c['disabled']),key=lambda c:c['rect']['x'])
    if len(choices)!=len(names):raise ValueError('Could not identify all acronym tiles.')
    centers=[c['rect']['y']+c['rect']['height']/2 for c in choices]
    if max(centers)-min(centers)>min(c['rect']['height'] for c in choices)/2:
        raise ValueError('Category tiles are not in one readable row.')
    return choices[indices[0]]['id']
