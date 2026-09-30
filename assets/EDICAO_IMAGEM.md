# Edição da fotografia da ponte

Ferramenta: image_gen integrada, modo de edição com transparent_background=true.
Entrada: fotografia anexada pelo usuário em 29/09/2026.
Saída escolhida: ponte_sem_fundo.png, com canal alfa; original não alterado.

## Prompt inicial

Use case: background-extraction. Edit target: supplied photograph of a silver metal laboratory truss bridge. Remove the entire laboratory background, including concrete floor, walls, yellow support beams and columns, ladder, bottle and cast shadow. Keep ONLY the complete silver truss bridge in the foreground, with all its thin braces, upper and lower chords, bolts, joints and two end frames. Preserve its exact geometry, perspective, metallic appearance and proportions from the original photo; do not redesign, straighten, add or remove bridge members. Make all spaces between members genuinely transparent as well as the outside background. Produce a clean photorealistic RGBA PNG cutout, framed tightly around the entire bridge with a small transparent margin, landscape composition. No checkerboard baked into pixels, no backdrop, no labels or added text.

## Prompt final de refinamento

Refine this background-extraction edit. Remove ONLY the leaning ladder protruding upwards from the far LEFT end of the bridge: the tall rectangular frame with horizontal ladder rungs above the bridge top chord is NOT part of the bridge. Make that area transparent. Keep the entire actual long horizontal silver truss bridge unchanged, including its left triangular end frame below the top chord, all braces, joints, bolts and right end. Clean any detached background specks around the outer edges and in openings. Preserve actual alpha transparency inside and outside truss openings. Do not crop any part of the bridge, leave a small transparent margin. No other changes.
