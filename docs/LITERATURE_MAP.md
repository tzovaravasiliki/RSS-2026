# Αρχικός χάρτης βιβλιογραφίας — 23 Οκτωβρίου 2026

Στοχευμένη αρχική ανασκόπηση πρωτογενών πηγών, όχι ολοκληρωμένο systematic review. Οι παρακάτω περιγραφές είναι παραφράσεις. Δεν τεκμηριώνουν απουσία προηγούμενης παρόμοιας εργασίας.

| Πηγή | Τι έχει ήδη εξεταστεί | Σχέση με το δικό μας ερώτημα | Τι πρέπει να συγκρίνουμε |
|---|---|---|---|
| Rosenthal, Veloso & Dey (2011), Task Behavior and Interaction Planning for a Mobile Service Robot that Occasionally Requires Help | Planning βοήθειας σε CoBot, ανθρώπινη διαθεσιμότητα/ακρίβεια και κόστος διακοπής | Η επιλογή ποιον/πότε να ρωτήσει το ρομπότ είναι ήδη αντικείμενο έρευνας | Μοντελοποίηση χρονικής ισχύος, ταυτότητας αντικειμένου, αντιφάσεων και κατανεμημένης ομαδικής γνώσης έναντι HOP-POMDP |
| Fang et al. (2026), Knowing When to Ask, arXiv:2603.07822v2 | Clarification για αβεβαιότητα που αλλάζει το πλάνο, cost-optimal querying, ρητά/άρρητα cues | Το «ρωτά μόνο όταν η απάντηση επηρεάζει την απόφαση» δεν αρκεί ως νέα ιδέα | Φορμαλισμός, planner, κόστος ερωτήσεων και αν υποστηρίζει πολλαπλές πηγές/παλαιές αναφορές |
| Gombolay et al. (RSS 2014), Decision-Making Authority, Team Efficiency and Human Worker Satisfaction in Mixed Human-Robot Teams | Κατανομή εξουσίας προγραμματισμού εργασιών και ανθρώπινη ομαδική αξιολόγηση | Χρήσιμη αφετηρία για ρομπότ ως συντονιστή και μετρήσεις πέρα από task success | Τι σημαίνει συντονισμός εργασίας έναντι απλής συζήτησης και πώς μετράμε ομαδική αποδοχή |
| Celino (HHAI 2026), Knowledge Affordances for Hybrid Human-AI Information Seeking | Εννοιολογική περιγραφή τι μπορεί να προσφέρει μία πηγή γνώσης σε συγκεκριμένο συγκείμενο | Αναδεικνύει ότι source selection απαιτεί σχετική γνώση και προσβασιμότητα, όχι μόνο ρόλο | Πρακτικός αλγόριθμος και εμπειρική αξιολόγηση έναντι εννοιολογικής πρότασης |
| Medroa, Saltan, Heining & Denecke (2025), VoiceCheck proof-of-concept | Offline φωνητική υποστήριξη χειρουργικών checklists, τεχνική αξιολόγηση και χρηστικότητα με 12 μέλη χειρουργικών ομάδων | Τεκμηριώνει σχετικό ιατρικό use case, όχι αυτομάτως την αποτελεσματικότητα uncertainty-aware coordination | Διαφορά checklist καταγραφής από αναζήτηση/επανεπιβεβαίωση κατανεμημένης γνώσης· δεν μεταφέρουμε ισχυρισμούς σε κλινικά outcomes |

## Πρωτογενείς σύνδεσμοι που ανοίχτηκαν ξανά για αυτή την έκδοση

1. [Rosenthal et al. — πλήρες κείμενο συγγραφέων](https://www.cs.cmu.edu/~mmv/papers/11aaaiw-stephanie.pdf).
2. [Fang et al. — abstract και μεταδεδομένα v2](https://arxiv.org/abs/2603.07822). Οι επιμέρους ποσοτικές επιδόσεις τους δεν χρησιμοποιούνται ως συγκρίσιμα αποτελέσματα του δικού μας pilot.
3. [Gombolay et al. — πλήρες άρθρο RSS](https://www.roboticsproceedings.org/rss10/p46.pdf).
4. [Celino — πλήρες άρθρο, DOI 10.3233/FAIA260524](https://journals.sagepub.com/doi/10.3233/FAIA260524).
5. [VoiceCheck — πλήρες άρθρο, DOI 10.1186/s13037-025-00460-0](https://link.springer.com/article/10.1186/s13037-025-00460-0).

## Προτεραιότητες επόμενης ανάγνωσης

- Λεπτομερής σύγκριση φορμαλισμού και baselines των Rosenthal και Fang. Καταγραφή τι ακριβώς αναπαριστούν ως αβεβαιότητα, πώς αποκτούν prior και πώς επιλέγουν ερωτήσεις.
- Kaupp et al. (2010), Human–robot communication for collaborative decision making — A probabilistic approach: [εκδοτική σελίδα](https://www.sciencedirect.com/science/article/pii/S0921889010000400). Το πλήρες κείμενο δεν έχει ελεγχθεί εδώ· παραμένει υποψήφιο, όχι τεκμήριο λεπτομερών ισχυρισμών.
- Li et al. (2026), Proactive collaboration via autonomous interaction: [DOI](https://doi.org/10.1038/s41467-026-72797-8). Χρειάζεται πλήρες κείμενο για να διακριθεί multi-robot από multi-human coordination. Δεν χρησιμοποιείται εδώ για ισχυρισμό πρωτοτυπίας.

## Σχέδιο ανασκόπησης

Αναζήτηση σε IEEE Xplore, ACM DL, Scopus/Web of Science, PubMed και arXiv, με διακριτό χαρακτηρισμό peer-reviewed/preprint. Αρχικά χωρίς κάτω χρονικό όριο, έως την ημερομηνία τελικής αναζήτησης. Ενδεικτικές ομάδες όρων:

```text
(robot* OR "human robot team") AND
("information seeking" OR "active clarification" OR "help seeking") AND
(uncertainty OR "value of information" OR "interruption cost")

("multi-human" OR "multi-party" OR "distributed knowledge") AND
(coordination OR "source selection" OR reverification)

("surgical checklist" OR "operating room" OR "medical protocol") AND
("voice assistant" OR "conversational agent" OR "AI coordinator")
```

Κριτήρια ένταξης: πρωτογενής μέθοδος ή αξιολόγηση σχετική με τουλάχιστον ένα από active querying, επιλογή πληροφοριοδότη, χρονική εγκυρότητα, team coordination ή ιατρική ομαδική υποστήριξη. Αποκλεισμός αμιγώς ατομικών chatbots χωρίς συνάφεια με πρωτόκολλο/συντονισμό, εκτός αν δίνουν άμεσα εφαρμόσιμη μέθοδο. Έρευνες και reviews χρησιμοποιούνται για ανακάλυψη πρωτογενών πηγών.

Για κάθε εργασία συμπληρώνουμε: task/ομάδα, ενσώματο σύστημα, τι είναι άγνωστο, μοντέλο γνώσης/αξιοπιστίας, source/time/object binding, ενέργειες ερώτησης, κόστος, δυνατότητα αντιφάσεων/αλλαγής κατάστασης, baselines, δεδομένα/συμμετέχοντες, μετρήσεις, περιορισμούς και διαθέσιμο κώδικα. Κρατάμε query, ημερομηνία, πλήθος αποτελεσμάτων, διπλότυπα και λόγους αποκλεισμού. Ακολουθεί backward/forward citation search των ισχυρότερων σχετικών άρθρων.

Παραδοτέο της ανασκόπησης: συγκριτικός πίνακας που ξεχωρίζει ήδη λυμένα στοιχεία από τεκμηριωμένα ανοικτά ερωτήματα. Η φράση «ρομπότ ως συντονιστής» δεν αρκεί ως διαφοροποίηση.

## Τεκμηρίωση υλοποίησης API

[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), έλεγχος 23/10/2026: χρησιμοποιείται root object με nested action union και πλήρη required πεδία. Η συμμόρφωση σε JSON schema δεν αποδεικνύει σημασιολογικά σωστή εξαγωγή· οι δύο έλεγχοι παραμένουν χωριστοί στον κώδικα.
