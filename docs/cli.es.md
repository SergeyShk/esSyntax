# El comando essyntax

``` bash
essyntax [opciones] [archivo ...]
```

El comando analiza texto de archivos o de la entrada estándar y escribe [CoNLL-U](https://universaldependencies.org/format.html): para cada palabra su lema, su categoría gramatical y sus rasgos, su núcleo y su relación de [Universal Dependencies](https://universaldependencies.org/). Se instala con el paquete (`pip install essyntax`) y también se ejecuta como `python -m essyntax`. El segmentador [anySeg](https://sergeyshk.github.io/anySeg/) divide el texto en oraciones, tokens y sus palabras, y el analizador morfológico [esMorph](https://sergeyshk.github.io/esMorph/es/) da las categorías gramaticales y los rasgos - las versiones instaladas con el paquete -, así que el resultado es el de [`parse_text`](parser.md#parse_text).

<!-- comparison: the speed of the command, one thread, words per second with the morphology (performance.md) -->

``` bash
echo "Mi madre lava la ropa." | essyntax
```

```
# newdoc
# newpar
# sent_id = 1
# text = Mi madre lava la ropa.
1	Mi	mi	DET	_	Number=Sing|Person=1|Poss=Yes|PronType=Prs	2	det	_	_
2	madre	madre	NOUN	_	Gender=Fem|Number=Sing	3	nsubj	_	_
3	lava	lavar	VERB	_	Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin	0	root	_	_
4	la	el	DET	_	Definite=Def|Gender=Fem|Number=Sing|PronType=Art	5	det	_	_
5	ropa	ropa	NOUN	_	Gender=Fem|Number=Sing	3	obj	_	SpaceAfter=No
6	.	.	PUNCT	_	PunctType=Peri	3	punct	_	_
```

## Opciones { #options }

| Opción | Por defecto | Descripción |
| :----- | :---------- | :---------- |
| `-i`, `--input` | `text` | [Entrada](#input): `text`, `conllu` |
| `-m`, `--model` | el modelo del paquete | Un archivo de modelo de esSyntax, como en [`Parser(path)`](parser.md#parameters) |
| `-o`, `--output` | la salida estándar | El archivo del resultado; `-` es la salida estándar |
| `-h`, `--help` | | Mostrar la ayuda (en inglés) |
| `-V`, `--version` | | Mostrar las versiones de esSyntax, anySeg y esMorph |

Los archivos se leen uno tras otro; sin archivos y en lugar de `-` se lee la entrada estándar. La entrada está en UTF-8: un archivo en otra codificación (Latin-1, cp1252, UTF-16) no se analiza, salvo que su primera letra con tilde llegue después de los primeros 64 KiB: entonces se analizan los párrafos de las partes de 64 KiB leídas antes de esa línea. Una sola línea con bytes no válidos se analiza con U+FFFD en su lugar. El valor de una opción se escribe aparte o junto: `-i conllu`, `-iconllu`, `--input=conllu`; un nombre de archivo que empieza por un guion va después de `--`. El texto se analiza por párrafos y CoNLL-U por oraciones: el resultado se escribe en cuanto una línea en blanco o el final de la entrada cierra el párrafo o la oración - en una terminal de inmediato, y a una tubería o un archivo cada vez que el comando espera la siguiente línea de entrada, así que se puede mantener abierto y darle texto párrafo a párrafo.

En Windows PowerShell 5.1 la redirección `>` y una canalización (`Get-Content text.txt | essyntax`) estropean las letras con tilde: pase el archivo como argumento y escriba el resultado con la opción `-o` (en PowerShell 7 también funcionan). El texto pasado con `echo` en cmd llega en la codificación de la consola: ejecute antes `chcp 65001`. Ni cmd ni PowerShell expanden los patrones de archivos (`*.txt`).

## Entrada { #input }

- `text` - texto: una línea en blanco termina un párrafo. El segmentador anySeg encuentra los tokens, sus palabras y las oraciones según las convenciones de Universal Dependencies con las que se entrenan los modelos de esMorph y esSyntax: `del` y `al` son dos palabras, y también un infinitivo o un gerundio con clíticos (`dárselo`); esMorph divide en palabras un token que el segmentador deja entero y cuyo análisis tiene varias (`Llévalo` es `Lleva` + `lo`). Una oración puede pasar de una línea a otra. Un párrafo sin líneas en blanco de más de 256 KiB (un archivo con una oración por línea, una sola línea larga) se analiza por partes que terminan en un límite de oración: la memoria no crece con la entrada, y los números de las oraciones y el párrafo continúan de una parte a otra; una oración de más de 256 KiB se corta.
- `conllu` - [CoNLL-U](https://universaldependencies.org/format.html) con categorías gramaticales (UPOS) y rasgos (FEATS): se rellenan las columnas HEAD y DEPREL, y las demás columnas, los comentarios, los tokens multipalabra y los nodos vacíos quedan como están (tampoco cambia la columna DEPS). Una categoría es una de las 17 categorías de UD en mayúsculas. Una oración en la que ninguna palabra tiene categoría pasa antes por esMorph: se rellenan LEMMA, UPOS y FEATS, y un token cuyo análisis tiene varias palabras las recibe, como con el comando `esmorph -i conllu`; una categoría en unas palabras de una oración pero no en todas es un error. El archivo se lee como con `anyseg.read_conllu`: los ID de las palabras van en orden, un token multipalabra tiene todas sus palabras, las formas coinciden con el comentario `text` si lo hay, y una oración tiene palabras. Es más estricto que `esmorph -i conllu`, que escribe una oración errónea tal cual y sigue: ante una línea errónea el análisis del archivo se detiene, las oraciones anteriores se escriben, y los archivos siguientes se analizan.

``` bash
printf '1\tElla\t_\tPRON\t_\tCase=Nom|Person=3\t_\t_\t_\t_\n2\tduerme\t_\tVERB\t_\tMood=Ind|Person=3\t_\t_\t_\t_\n' | essyntax -i conllu
```

```
1	Ella	_	PRON	_	Case=Nom|Person=3	2	nsubj	_	_
2	duerme	_	VERB	_	Mood=Ind|Person=3	0	root	_	_
```

El modelo está entrenado con las etiquetas de esMorph, y los rasgos deben estar completos; con las etiquetas de referencia de los treebanks el LAS en las palabras de referencia de AnCora dev y GSD dev es 0.4 y 1.4 puntos más alto. Para sustituir la morfología de un archivo CoNLL-U por la de esMorph y analizarlo, encadene los comandos:

``` bash
esmorph -i conllu -f conllu gold.conllu | essyntax -i conllu > parsed.conllu
```

## Salida { #output }

CoNLL-U tal como lo escribe anySeg. Para la entrada `text` es el del comando `esmorph -f conllu` con HEAD y DEPREL rellenos: un archivo empieza con el comentario `newdoc`, un párrafo con `newpar`, una oración tiene los comentarios `sent_id` (numerados a lo largo de todos los archivos) y `text`; MISC tiene `SpaceAfter=No` en un token sin espacio detrás dentro de su párrafo y `SpacesAfter` donde el espacio no es uno solo, y la sangría de un párrafo es `SpacesBefore` de su primer token. Un token multipalabra es una línea con el rango de sus palabras (`1-2`) y la forma del token, seguida de las líneas de sus palabras; los núcleos y las relaciones son los de las palabras, así que la línea del token conserva `_` en HEAD y DEPREL. Para la entrada `conllu` una oración se escribe tal como se leyó, con los núcleos y las relaciones nuevos. Las líneas terminan en LF, y el texto está en UTF-8.

``` bash
echo "Llévalo al coche." | essyntax
```

```
# newdoc
# newpar
# sent_id = 1
# text = Llévalo al coche.
1-2	Llévalo	_	_	_	_	_	_	_	_
1	Lleva	llevar	VERB	_	Mood=Imp|Number=Sing|Person=2|VerbForm=Fin	0	root	_	_
2	lo	él	PRON	_	Case=Acc|Gender=Masc|Number=Sing|Person=3|PrepCase=Npr|PronType=Prs	1	obj	_	_
3-4	al	_	_	_	_	_	_	_	_
3	a	a	ADP	_	_	5	case	_	_
4	el	el	DET	_	Definite=Def|Gender=Masc|Number=Sing|PronType=Art	5	det	_	_
5	coche	coche	NOUN	_	Gender=Masc|Number=Sing	1	obl:arg	_	SpaceAfter=No
6	.	.	PUNCT	_	PunctType=Peri	1	punct	_	_
```

## Códigos de salida { #exit-codes }

| Código | Cuándo |
| :----- | :----- |
| 0 | Éxito, también cuando la salida se cierra antes del final (`essyntax text.txt \| head`) |
| 1 | Un archivo de entrada no existe, no se puede leer o no está en UTF-8, una línea no está en UTF-8 (se analiza con U+FFFD), una línea de CoNLL-U es errónea o una categoría es desconocida; las oraciones anteriores al error se analizan, y también los demás archivos |
| 1 | El modelo no se puede leer, el archivo de salida no se puede crear o es un archivo de entrada o el archivo del modelo; no se analiza nada |
| 1 | Un error de escritura; el análisis se detiene |
| 2 | Opciones no válidas |

Los mensajes de error van a la salida de errores, en inglés, con el archivo y la línea:

``` bash
printf '1\tElla\t_\tPRON\t_\t_\t_\t_\t_\t_\n2\tduerme\t_\t_\t_\t_\t_\t_\t_\t_\n' | essyntax -i conllu
```

```
essyntax: -: line 2: the word has no part of speech, while other words of the sentence do
```
