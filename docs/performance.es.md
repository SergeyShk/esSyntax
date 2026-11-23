# Comparación

Desde el texto en bruto esSyntax analiza con más precisión que spaCy, incluido su modelo de transformer, y que UDPipe 1 en los cuatro conjuntos de prueba: 2.8-6.5 puntos de LAS más que spaCy `es_dep_news_trf` y 5.9-12.5 más que los demás. Está a la par del modelo por defecto de Stanza en AnCora y COSER y por detrás de él en GSD y PUD, cuyas convenciones ese modelo aprende de GSD; supera al modelo AnCora de Stanza en GSD y PUD y queda 1.2-1.7 puntos por detrás de él en AnCora y COSER; Stanza accurate, con un transformer, va por delante en los cuatro conjuntos. A la vez esSyntax analiza 31 mil palabras por segundo en un hilo junto con las etiquetas de esMorph - casi tan rápido como los modelos de spaCy sin transformer, 23 veces más rápido que spaCy `es_dep_news_trf` y 27 veces más rápido que Stanza -, se carga en 0.01 s y necesita 120 MB de memoria, 6 veces menos que el modelo más pequeño de spaCy.

## Calidad { #quality }

El estándar de referencia son las partes de prueba de los treebanks [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora), [GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD), [PUD](https://github.com/UniversalDependencies/UD_Spanish-PUD) y [COSER](https://github.com/UniversalDependencies/UD_Spanish-COSER) de la versión UD 2.19: noticias, textos de la web, oraciones de noticias y de Wikipedia traducidas de otras lenguas y habla rural. Las métricas son las del script oficial de evaluación de [CoNLL 2018](https://universaldependencies.org/conll18/evaluation.html): UAS es la proporción de palabras con el núcleo correcto, y LAS, con el núcleo y la relación correctos (sin su subtipo); los signos de puntuación se cuentan. Los treebanks siguen convenciones distintas, así que hay que comparar los sistemas en un mismo conjunto, y no los conjuntos entre sí.

Con qué se entrenaron los modelos:

- esSyntax: las partes de entrenamiento de AnCora y GSD, y analiza con las convenciones de AnCora;
- spaCy `es_core_news_sm`, `es_core_news_md`, `es_core_news_lg` y el modelo de transformer `es_dep_news_trf`: AnCora;
- Stanza (el paquete `default`) y Stanza accurate (`default_accurate`, con el transformer bertin-roberta-base-spanish): AnCora y GSD;
- Stanza ancora (el paquete `ancora`): AnCora;
- UDPipe 1: AnCora de UD 2.5.

AnCora es el conjunto propio de todos los sistemas. PUD y GSD fueron anotados por Google con las mismas pautas, así que los modelos que aprenden las convenciones de GSD, Stanza y Stanza accurate, van por delante también en PUD. COSER, habla rural transcrita, es nuevo para todos ellos. UDPipe 2, un servicio web, y trankit no se comparan.

### Texto en bruto { #raw }

Cada sistema divide el texto en oraciones, tokens y palabras por sí mismo, como trabaja para el usuario; esSyntax lo hace con `parse_text` (anySeg y esMorph). UAS / LAS, %:

| Sistema | AnCora | GSD | PUD | COSER |
| :------ | -----: | --: | --: | ----: |
| esSyntax | 91.94 / 89.25 | 87.06 / 80.95 | 89.57 / 81.97 | 73.66 / 65.52 |
| spaCy es_core_news_sm | 84.07 / 79.77 | 77.96 / 70.48 | 81.90 / 72.82 | 68.08 / 59.24 |
| spaCy es_core_news_md | 84.73 / 80.63 | 78.46 / 71.23 | 82.45 / 73.63 | 68.07 / 59.64 |
| spaCy es_core_news_lg | 84.81 / 80.84 | 78.15 / 70.99 | 82.73 / 73.83 | 66.53 / 58.37 |
| spaCy es_dep_news_trf | 88.46 / 85.01 | 81.40 / 74.45 | 84.84 / 75.85 | 71.22 / 62.73 |
| Stanza | 91.72 / 89.19 | 89.32 / 84.89 | 90.43 / 83.99 | 73.44 / 65.43 |
| Stanza ancora | 92.92 / **90.90** | 86.12 / 80.20 | 89.30 / 81.41 | 73.90 / **66.76** |
| Stanza accurate | 92.97 / 90.67 | 91.02 / **87.14** | 91.34 / **85.17** | 74.57 / 66.47 |
| UDPipe 1 | 84.12 / 78.73 | 77.28 / 68.48 | 82.15 / 72.19 | 67.10 / 58.24 |

Un error en las palabras o en las oraciones pasa al análisis. spaCy no divide en palabras `del`, `al` ni un verbo con sus clíticos, y UDPipe 1 divide solo algunos: de las palabras de referencia al texto en bruto pierden 2.1-4.2 puntos de LAS, mientras que esSyntax y Stanza pierden 0.1-0.8 fuera de COSER. COSER es habla transcrita sin párrafos, y en él todos los sistemas encuentran peor los límites de las oraciones.

??? note "Palabras y oraciones"

    F1 de palabras / oraciones, %:

    | Sistema | AnCora | GSD | PUD | COSER |
    | :------ | -----: | --: | --: | ----: |
    | esSyntax (anySeg y esMorph) | 99.93 / 98.66 | 99.90 / 90.97 | 99.77 / 98.80 | 99.76 / 83.82 |
    | spaCy es_core_news_sm | 96.60 / 97.70 | 96.39 / 88.14 | 96.60 / 97.34 | 98.41 / 82.65 |
    | spaCy es_core_news_md | 96.60 / 97.42 | 96.39 / 86.99 | 96.60 / 96.89 | 98.41 / 81.26 |
    | spaCy es_core_news_lg | 96.60 / 97.33 | 96.39 / 87.85 | 96.60 / 96.89 | 98.41 / 79.88 |
    | spaCy es_dep_news_trf | 96.60 / 98.96 | 96.39 / 95.62 | 96.60 / 99.20 | 98.41 / 89.47 |
    | Stanza | 99.95 / 98.78 | 99.81 / 93.44 | 99.66 / 98.20 | 99.54 / 79.21 |
    | Stanza ancora | 99.97 / 98.95 | 99.72 / 90.62 | 99.73 / 98.45 | 99.62 / 83.38 |
    | Stanza accurate | 99.95 / 98.34 | 99.79 / 93.67 | 99.65 / 98.35 | 99.53 / 80.12 |
    | UDPipe 1 | 97.12 / 98.32 | 96.83 / 89.18 | 96.96 / 97.60 | 98.66 / 73.99 |

### Palabras de referencia { #words }

Los sistemas reciben las palabras y las oraciones de referencia, con `del` como `de` y `el` y un verbo aparte de sus clíticos, y las etiquetan ellos mismos (esSyntax, con las etiquetas de esMorph en contexto): así se ve el análisis sin los errores de la división. UAS / LAS, %:

| Sistema | AnCora | GSD | PUD | COSER |
| :------ | -----: | --: | --: | ----: |
| esSyntax | 92.15 / 89.44 | 87.83 / 81.68 | 89.85 / 82.21 | 75.39 / 67.03 |
| spaCy es_core_news_sm | 87.64 / 82.93 | 82.24 / 74.35 | 85.34 / 75.79 | 71.00 / 61.79 |
| spaCy es_core_news_md | 88.34 / 83.91 | 82.67 / 74.90 | 85.87 / 76.64 | 71.01 / 62.24 |
| spaCy es_core_news_lg | 88.40 / 84.14 | 82.59 / 74.96 | 86.24 / 76.90 | 70.25 / 61.59 |
| spaCy es_dep_news_trf | 92.33 / 88.57 | 85.87 / 78.42 | 88.30 / 78.82 | 73.62 / 64.83 |
| Stanza | 91.86 / 89.32 | 90.02 / 85.51 | 90.85 / 84.37 | 75.99 / 67.74 |
| Stanza ancora | 93.02 / **91.00** | 87.02 / 80.98 | 89.59 / 81.64 | 75.98 / 68.67 |
| Stanza accurate | 93.12 / 90.82 | 91.68 / **87.78** | 91.74 / **85.52** | 77.22 / **68.77** |
| UDPipe 1 | 86.91 / 81.39 | 81.08 / 71.96 | 84.97 / 75.03 | 71.70 / 62.41 |

Cada sistema etiqueta las palabras con su propio etiquetador, como lo hace para el usuario. Los analizadores de Stanza leen además las etiquetas finas de AnCora (XPOS) de su etiquetador, que esMorph no da, así que los sistemas no se comparan con la misma morfología.

## Velocidad { #speed }

El análisis de las palabras de referencia de la parte de prueba de AnCora (53 622 palabras) en un hilo, el mejor de dos análisis sin la carga; esSyntax, junto con las etiquetas de esMorph. La carga es la importación y la creación del analizador con el análisis de la primera oración; la memoria, el pico del proceso.

| Sistema | Palabras/s | Carga, s | Memoria, MB |
| :------ | ---------: | -------: | ----------: |
| esSyntax | 31 253 | **0.01** | **120** |
| spaCy es_core_news_sm | **34 069** | 1.77 | 743 |
| spaCy es_core_news_md | 31 697 | 1.96 | 955 |
| spaCy es_core_news_lg | 31 484 | 2.03 | 1525 |
| spaCy es_dep_news_trf | 1332 | 2.48 | 2642 |
| Stanza | 1143 | 2.85 | 3535 |
| Stanza ancora | 1146 | 2.90 | 3592 |
| Stanza accurate | 424 | 3.98 | 4150 |
| UDPipe 1 | 6155 | 0.82 | 222 |

spaCy recibe las palabras como un `Doc` ya hecho, y esSyntax, como un documento de anySeg; ambos las etiquetan antes del análisis. Stanza accurate se midió con las primeras 20 034 palabras. El pico de memoria depende de la cantidad de texto por llamada: los demás sistemas recibieron toda la parte de prueba de AnCora en una llamada, así que la memoria de Stanza accurate no se compara con la suya. El ordenador es un Apple M3 Pro con macOS 26 y otras aplicaciones abiertas: la carga media de 1 minuto era inferior a 4 (3.3-4.0) antes de cada medición. esSyntax y spaCy `es_core_news_sm`, medidos uno tras otro tres veces, dieron 31 253-31 401 y 32 663-34 069 palabras por segundo.

## Cómo reproducir { #reproduce }

El script `scripts/compare.py` descarga las partes de prueba de los treebanks, el script de evaluación de CoNLL 2018 y los modelos de los demás sistemas comprobando su SHA-256 (los modelos de Stanza, con su propio descargador, y después las sumas de control de sus archivos), analiza los conjuntos con cada sistema y calcula las métricas, mide la velocidad, la carga y la memoria en un proceso aparte para cada sistema y escribe las tablas. El texto en bruto de un conjunto es el texto de sus oraciones por párrafos; GSD y COSER no tienen párrafos y son un solo texto cada uno. Las versiones de los paquetes están fijadas en `scripts/compare.py.lock`; esSyntax se toma de un wheel construido desde el repositorio, y esMorph y anySeg se fijan en la orden (sus versiones se guardan en los resultados):

``` bash
rm -rf target/compare/wheels
uvx maturin@1.15.0 build --release --locked -o target/compare/wheels
uvx uv@0.13.5 run --with target/compare/wheels/essyntax-*.whl --with esmorph==0.6.0 --with anyseg==0.5.0 \
    scripts/compare.py target/compare
```

Versiones: Python 3.11, esMorph 0.6.0, anySeg 0.5.0, spaCy 3.8.16 con los modelos 3.8.0 sin NER, Stanza 1.15.0 con sus modelos 1.15.0 en la CPU (torch 2.14.1, transformers 4.57.6), UDPipe 1.4.0.1 con el modelo `spanish-ancora-ud-2.5-191206`.
