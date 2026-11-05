\set ON_ERROR_STOP on
BEGIN;
INSERT INTO corpora(id,name,corpus_kind) VALUES ('test-c','synthetic','bible');
INSERT INTO works(id,corpus_id,title) VALUES ('test-w','test-c','synthetic');
INSERT INTO reference_schemes(id,corpus_id,scheme_name) VALUES ('test-a','test-c','A'),('test-b','test-c','B');
INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity) VALUES
('a1','test-c','test-w','test-a','1:1','verse'),('a2','test-c','test-w','test-a','1:2','verse'),
('b1','test-c','test-w','test-b','1:1','verse'),('b2','test-c','test-w','test-b','1:2','verse');
INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,rationale) VALUES
('l1','a1','b1','partial','synthetic'),('l2','a1','b2','partial','synthetic'),('l3','a2','b1','overlapping','synthetic');
DO $$ BEGIN
 IF (SELECT count(*) FROM passage_alignments WHERE from_passage_id='a1') <> 2 OR (SELECT count(*) FROM passage_alignments WHERE to_passage_id='b1') <> 2 THEN RAISE EXCEPTION 'many-to-many failed'; END IF;
 RAISE NOTICE 'PASS: address mapping many-to-many in both query directions';
 BEGIN INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,rationale) VALUES ('bad','a1','missing','partial','synthetic'); RAISE EXCEPTION 'missing foreign key accepted'; EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'PASS: alignment foreign key'; END;
 BEGIN INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity) VALUES ('dupe','test-c','test-w','test-a','1:1','verse'); RAISE EXCEPTION 'duplicate address accepted'; EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'PASS: address uniqueness'; END;
 BEGIN INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,rationale) VALUES ('same','a1','a1','partial','synthetic'); RAISE EXCEPTION 'self mapping accepted'; EXCEPTION WHEN check_violation THEN RAISE NOTICE 'PASS: self alignment check'; END;
END $$;
INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,rationale) VALUES ('duplicate-link','a1','b1','partial','synthetic');
\echo 'OBSERVATION: duplicate from/to/type alignment accepted; missing uniqueness constraint remains documented'
ROLLBACK;
