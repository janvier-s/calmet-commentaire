import json

data = {
  "book_title": None,
  "chapter_title": "CHAPITRE IX.",
  "chapter_summary": "_Job avouë que l'homme n'est qu'injustice, comparé à Dieu. Mais il soutient que Dieu afflige l'innocent, de même que le coupable. Il défend son innocence, et expose son affliction._",
  "verses": [
    {
      "verse_number": 1,
      "latin": "ET reſpondens Job, ait :",
      "french": "Ob répondit à Baldad :",
      "annotations": []
    },
    {
      "verse_number": 2,
      "latin": "Vere ſcio quod ita ſit, & quod non juſtificetur homo compoſitus Deo.",
      "french": "Je sçai que cela est ainsi, et que l'homme, si on le compare avec Dieu, ne sera point juste.",
      "annotations": []
    },
    {
      "verse_number": 3,
      "latin": "Si voluerit contendere cum eo, non poterit ei reſpondere unum pro mille.",
      "french": "S'il veut disputer contre Dieu, de mille accusations, il n'y en aura pas une sur quoi il puisse répondre.",
      "annotations": []
    }
  ],
  "commentary": [
    {
      "commentary_id": 1,
      "verse_ref": "℣. 21.",
      "latin_quote": "DONEC IMPLEATUR RISU OS TUUM.",
      "french_translation": "_Jusqu'à ce que la joye se répande sur vôtre visage_",
      "french_commentary": "Le Seigneur ne vous abandonnera pas, si vous vivez dans la justice ; il vous rétablira dans vôtre premier état, et vous rendra la joye, et la paix dont vous joüissiez auparavant. celui qui est simple. Ou, suivant l'Hébreu :^{(a)} il ne méprisera point celui qui est parfait, irreprochable, sans défauts ; le juste, l'homme vraiment pieux."
    },
    {
      "commentary_id": 2,
      "verse_ref": "℣. 2.",
      "latin_quote": "VERE SCIO QUOD ITA SIT.",
      "french_translation": "_Je sçai que cela est ainsi._",
      "french_commentary": "Job répond aux principes établis par Eliphaz,^{(b)} et par Baldad,^{(c)} que Dieu ne punit jamais un innocent ; et il y répond avec une humilité, et une piété admirables. Il avouë que Dieu est infiniment juste, et que toute la justice de l'homme n'est rien en sa présence ; que si Dieu nous traite avec rigueur, et suivant nos seuls mérites, nous méritons toute sorte de châtimens, puisque nous ne sommes qu'infirmité, que péché, et que corruption par nous-mêmes : mais quoiqu'il reconnoisse humblement devant Dieu qu'il est pécheur, il soutient que devant les hommes, et à leur jugement, il n'a commis aucune injustice. Il est dans les dispositions où était saint Paul,"
    }
  ],
  "footnotes": [
    {
      "marker": "(a)",
      "text": "[UNCERTAIN HEBREW] לא ימאס תם"
    },
    {
      "marker": "(b)",
      "text": "Job. IV. 7."
    },
    {
      "marker": "(c)",
      "text": "Job. VIII. 3."
    }
  ]
}

with open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/20_job/normalized/page_0151.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
