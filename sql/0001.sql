DROP TABLE IF EXISTS senders;
CREATE TABLE senders (sender VARCHAR(255), action VARCHAR(16), ref VARCHAR(255), source VARCHAR(64), type CHAR(1), PRIMARY KEY (sender));

DROP TABLE IF EXISTS senders_static;
CREATE TABLE senders_static (sender VARCHAR(255), action VARCHAR(16), ref VARCHAR(255), source VARCHAR(64), type CHAR(1), PRIMARY KEY (sender));

DROP INDEX IF EXISTS stash_senders;
DROP TABLE IF EXISTS stash;

CREATE TABLE stash (id BIGSERIAL, created TIMESTAMP WITH TIME ZONE DEFAULT now(), sender VARCHAR(255), recipients TEXT, message TEXT, PRIMARY KEY (id));
CREATE INDEX stash_senders ON stash (sender);

DROP INDEX IF EXISTS stash_static_senders;
DROP TABLE IF EXISTS stash_static;

CREATE TABLE stash_static (id BIGSERIAL, created TIMESTAMP WITH TIME ZONE DEFAULT now(), sender VARCHAR(255), recipients TEXT, message TEXT, PRIMARY KEY (id));
CREATE INDEX stash_static_senders ON stash_static (sender);

DROP TABLE IF EXISTS challenges;
CREATE TABLE challenges (challenge VARCHAR(255), action_to_take VARCHAR(16), source VARCHAR(64), challenge_type CHAR(1), PRIMARY KEY (challenge));

DROP TABLE IF EXISTS config;
CREATE TABLE config (name VARCHAR(255), value VARCHAR(255), PRIMARY KEY(name));
INSERT INTO config (name, value) VALUES ('schema', '1');
