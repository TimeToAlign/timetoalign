EEP dataset: dataset of a ensemble expressive performances
==========================================================

Created by
----------

Esteban Maestre^, Marco Marchini*, Panos Papiotis*, Alfonso Perez*
* Music Technology Group, Universitat Pompeu Fabra, Barcelona, Spain
http://mtg.upf.edu/
^ Computational Acoustics Modeling Lab, Music Tech Center for Interdisciplinary Research in Music Media and Technology
Schulich School of Music, McGill University, Montréal
http://www.music.mcgill.ca/caml
http://www.cirmmt.org


Description
-----------

The dataset contains 23 recordings of string quartet performance. The recordings were made as part of the experiments on ensemble expressive performance reported in the following article:

Marco Marchini, Rafael Ramirez, Panos Papiotis, and Esteban Maestre. "The sense of ensemble: a machine learning approach to expressive performance modelling in string quartets". Journal of New Music Research, 43 (3):303–317, 2014.

The recordings contain five extracts from Beethoven’s Concerto N.4, Op. 18:
I) Allegro-Prestissimo movement,
P1) Allegro ma non tanto movement (bars 54-78)
P2) Allegro ma non tanto movement (bars 138-151)
P3) Menuetto (bars 8-50)
P4) Allegro-Prestissimo (bars 28-45)

The piece (I) was recorded 3 times with increasing degrees of expressiveness:
• Mechanical
• Normal interpreted
• Exaggerated

The pieces (P.1-P.4) were recorded 5 times each:
• Ensemble performance
• Solo performance of Violin 1
• Solo performance of Violin 2
• Solo performance of Viola
• Solo performance of Cello

The musicians have given their explicit approval for this dataset to be made public.
For more info about the research on ensemble expressive performance visit: www.mmarchini.com


Structure of the dataset
------------------------

We created a RepoVizz datapack for each of the recording which can be browsed at: http://repovizz.upf.edu/

The datapacks are the following:

StringQuartetEEP_P1_Ensemble
StringQuartetEEP_P1_SoloVl1
StringQuartetEEP_P1_SoloVl2
StringQuartetEEP_P1_SoloViola
StringQuartetEEP_P1_SoloCello
StringQuartetEEP_P2_Ensemble
StringQuartetEEP_P2_SoloVl1
StringQuartetEEP_P2_SoloVl2
StringQuartetEEP_P2_SoloViola
StringQuartetEEP_P2_SoloCello
StringQuartetEEP_P3_Ensemble
StringQuartetEEP_P3_SoloVl1
StringQuartetEEP_P3_SoloVl2
StringQuartetEEP_P3_SoloViola
StringQuartetEEP_P3_SoloCello
StringQuartetEEP_P4_Ensemble
StringQuartetEEP_P4_SoloVl1
StringQuartetEEP_P4_SoloVl2
StringQuartetEEP_P4_SoloViola
StringQuartetEEP_P4_SoloCello
StringQuartetEEP_I_Mechanical
StringQuartetEEP_I_Normal
StringQuartetEEP_I_Exaggerated

Each performance folder contains audio files, score alignment files and bowing motion descriptors and raw instrumental motion capture.

Audio Files
-----------

Each recording contains two ambient audio tracks in the "Ambient Audio" node: a cardioid microphone and a binaural microphone (this file is best experienced with headphones).

In addition, each recording includes contact microphone recording of each musician in separate tracks. These audios are included in the "Pickup Audio" node.

Score alignment
---------------

We place a score-performance alignment file per musician in the "Score Alignment" node of each datapack.
If downloaded, the score alignment file can be opened with a text editor and is written in human readable format. It contains, for each performed note a line like the following:

onsetTimeInSeconds offsetTimeInSeconds pitchContent

The original score by Beethoven can be retrieved in various formats here:
http://imslp.org/wiki/String_Quartet_No.4,_Op.18_No.4_(Beethoven,_Ludwig_van)

Polhemus MoCap Data
-------------------

Bowing motion descriptors are placed in the "Instrument Gestures" node of each datapack. Within this node the bowing descriptors relative to each musicians are places on separate nodes.
The raw Polhemus mocap data is found on the "Polhemus MoCap data" node and can be visualized by dragging such node to the first pane of in RepoVizz.


Please Acknowledge MTG-EEP in Academic Research
-----------------------------------------------

When the MTG-EEP dataset is used for academic research, we would highly appreciate if scientific publications of works partly based on the MTG-EEP dataset cite the following publication:

Marco Marchini, Rafael Ramirez, Panos Papiotis, and Esteban Maestre. "The sense of ensemble: a machine learning approach to expressive performance modelling in string quartets". Journal of New Music Research, 43 (3):303–317, 2014.

Conditions of Use
-----------------

Dataset compiled and authored by Esteban Maestre, Marco Marchini, Panos Papiotis and Alfonso Perez. Copyright © 2014 Music Technology Group, Universitat Pompeu Fabra. All Rights Reserved.

The MTG EEP dataset is offered free of charge for internal non-commercial use only. You may not redistribute, publically communicate or modify it. Please see the license terms in the README file within the dataset for applicable conditions.

Feedback
--------

Problems, positive feedback, negative feedback... it is all welcome! Please help us improve MTG-EEP by sending your feedback to: mtg@upf.edu
In case of a problem report please include as many details as possible.
