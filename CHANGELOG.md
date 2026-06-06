# Changelog

## [0.29.0](https://github.com/chio-labs/sqlbuild/compare/v0.28.0...v0.29.0) (2026-06-06)


### Features

* add accepted values and relationships audits ([7a12fd3](https://github.com/chio-labs/sqlbuild/commit/7a12fd3098dfe885a73f7a8922daa28e3893a1e0))
* add bigquery and databricks freshness metadata ([875796d](https://github.com/chio-labs/sqlbuild/commit/875796d1990dda1ec590854a6367d0af4660b85b))
* add cli document helper ([bbbb2cb](https://github.com/chio-labs/sqlbuild/commit/bbbb2cbf35e407b6899052723f7cdaac5c331918))
* add coded error messages ([2ef3512](https://github.com/chio-labs/sqlbuild/commit/2ef35120173d55d2c1c60c323fbacf40079e9975))
* add column lineage analyzer ([f60c65d](https://github.com/chio-labs/sqlbuild/commit/f60c65d1b4fd7d7d9512d75023f829888e555fb6))
* add column lineage CLI traces ([83977a0](https://github.com/chio-labs/sqlbuild/commit/83977a048fe6dc978909b85ddbf1c619ba39468f))
* add compile contract diagnostics ([0ba4d65](https://github.com/chio-labs/sqlbuild/commit/0ba4d65e66a1df8b519ac62a6b9e2941f0998b83))
* add concurrent load and seed execution ([0efa072](https://github.com/chio-labs/sqlbuild/commit/0efa072d3193a5f9ff3503ad25b11ef41aa2421b))
* add concurrent loader dag scheduling ([2bb66e9](https://github.com/chio-labs/sqlbuild/commit/2bb66e976d040ba481ea75eb7aea78ff25cf1c77))
* add conservative nullability inference ([74b6bb2](https://github.com/chio-labs/sqlbuild/commit/74b6bb22a614fae5c106a48032e54107b0b8a479))
* add contract config surface ([b1648b1](https://github.com/chio-labs/sqlbuild/commit/b1648b16ede32e9bce6d66cf8627cb8f38cf543a))
* add Dagster asset loader ([6cf6e29](https://github.com/chio-labs/sqlbuild/commit/6cf6e29cb5c4887f2fa7e82bee60bd34768fc0e6))
* add Dagster CLI resource ([c718d55](https://github.com/chio-labs/sqlbuild/commit/c718d55a706e2e205722e548ec3ee5a9346d4019))
* add Dagster playground template ([718e77d](https://github.com/chio-labs/sqlbuild/commit/718e77d2cbc14d6760b7af5dac50d1249ef234db))
* add Dagster project preparation ([df92013](https://github.com/chio-labs/sqlbuild/commit/df9201367a8359fd838c12f142941d4e7a3c11b2))
* add Dagster scenario checks helper ([75473bd](https://github.com/chio-labs/sqlbuild/commit/75473bd36455132be1df12d25a737aa112c9e10a))
* add dbt interop debug ([8d71604](https://github.com/chio-labs/sqlbuild/commit/8d7160440446e9a242c3a67b028f50e15a8b7134))
* add dbt interop foundation ([6d548b9](https://github.com/chio-labs/sqlbuild/commit/6d548b9c386895e707fcbb3a118f24bfc9cb6c26))
* add dbt interop plan output ([9e5d012](https://github.com/chio-labs/sqlbuild/commit/9e5d0123001a9530e307e97ba485d7a88d2763cc))
* add direct source freshness state ([4cc989c](https://github.com/chio-labs/sqlbuild/commit/4cc989cf7ec4c923e2715ae1cec31f133d3163f9))
* add fast compile lineage mode ([19fb926](https://github.com/chio-labs/sqlbuild/commit/19fb9261d13bb1947b990fe35a5363957cca2bc7))
* add incremental source loader writes ([d4a598b](https://github.com/chio-labs/sqlbuild/commit/d4a598bbe316f4f4d1132ffc0e2a20bb46067029))
* add ingestr integration loaders ([d824860](https://github.com/chio-labs/sqlbuild/commit/d824860cb186b9a069e42c629b3680180fdd0552))
* add lineage mode metadata ([726ebb0](https://github.com/chio-labs/sqlbuild/commit/726ebb04fa08178dbf323ad1632e03c341272af4))
* add loader cursor override context ([44abb1b](https://github.com/chio-labs/sqlbuild/commit/44abb1b9af224153011bc78fb8fa6ebd4374cd2e))
* add local scenario load-only test ([a85f305](https://github.com/chio-labs/sqlbuild/commit/a85f3058509cd421c3f1f8a1cbe09930b2bc0b7c))
* add macro SQL test mode ([6498527](https://github.com/chio-labs/sqlbuild/commit/64985278ed1fb46d6af50d15e24f09eea8e2d544))
* add macro SQL test mode ([1e6c6c6](https://github.com/chio-labs/sqlbuild/commit/1e6c6c6904c1b304d5c39c11d1464c6103f5a075))
* add MotherDuck adapter ([403d536](https://github.com/chio-labs/sqlbuild/commit/403d536c0af1a65ed793d3dc6744fb923c32e1a3))
* add MotherDuck adapter ([36b70ef](https://github.com/chio-labs/sqlbuild/commit/36b70ef0746954db09a6755e79dd9d1ba585f947))
* add nullable contracts and built-in audits ([611f99a](https://github.com/chio-labs/sqlbuild/commit/611f99a689440b29af5ebe835e27de6967c60d8d))
* add PostgreSQL adapter ([2b7b1c5](https://github.com/chio-labs/sqlbuild/commit/2b7b1c5822a75eda23ab1610541ce8cdcb998802))
* add PostgreSQL adapter ([a01fcca](https://github.com/chio-labs/sqlbuild/commit/a01fccafb8e896e57af8c22e3e0e3e660d6f1a12))
* add python check result context ([8542fcc](https://github.com/chio-labs/sqlbuild/commit/8542fcc270063f4dc9eb0d591f2438ffbc6bd30c))
* add python node contexts ([00536e7](https://github.com/chio-labs/sqlbuild/commit/00536e73330bb7abbcf85035062164fc2e640841))
* add python node executor ([4bed0fb](https://github.com/chio-labs/sqlbuild/commit/4bed0fba89e9b3c9aade7483aa3818f8b99eaf3a))
* add python node factories ([ba64a5d](https://github.com/chio-labs/sqlbuild/commit/ba64a5dcc221bcf6d106b4dd69bd97d352696476))
* add python node factories ([7386f73](https://github.com/chio-labs/sqlbuild/commit/7386f7392d98317b1f464044541218409bb0fa82))
* add python node foundation ([6f0a20f](https://github.com/chio-labs/sqlbuild/commit/6f0a20f67bef9f33dd735b133daba660f51ef5c7))
* add python node graph inventory ([e8ffa75](https://github.com/chio-labs/sqlbuild/commit/e8ffa75aa457220d092f91049879cae005e5d854))
* add python node result policies ([dec97fe](https://github.com/chio-labs/sqlbuild/commit/dec97fed017095d20f4f043393cff5f6d8405d5d))
* add python node retry policy ([ba2303a](https://github.com/chio-labs/sqlbuild/commit/ba2303a3bfe29e7b0c1e54516848dee1c4f80aa5))
* add python node selector resolver ([3bd4339](https://github.com/chio-labs/sqlbuild/commit/3bd433961a9e4141ae971465860d3c531002b841))
* add python nodes playground ([f6114b1](https://github.com/chio-labs/sqlbuild/commit/f6114b19bde901aa87e8a735619649772eea95d3))
* add rivers integration ([82de30c](https://github.com/chio-labs/sqlbuild/commit/82de30ca29f4cde1deba35f08d6575fa82657c62))
* add rivers integration ([9268beb](https://github.com/chio-labs/sqlbuild/commit/9268beb1cae3bd78f51f9e17241767c892d51722))
* add scenario capture command ([f98d0eb](https://github.com/chio-labs/sqlbuild/commit/f98d0eb0b7dfcf414bc15266fe1bb4377e1b48e1))
* add scenario capture safety limits ([f1660f7](https://github.com/chio-labs/sqlbuild/commit/f1660f74104e3d1f7618ee35673f8d7b276a0e8b))
* add scenario error codes ([666e108](https://github.com/chio-labs/sqlbuild/commit/666e1082b39828d10b893b716b878399b1db4ffc))
* add scenario snapshot JSONL helpers ([f0402d0](https://github.com/chio-labs/sqlbuild/commit/f0402d0fba328d2d448365f49f0eaea4969cfad4))
* add scenario snapshot primitives ([b76623e](https://github.com/chio-labs/sqlbuild/commit/b76623e4c0cde009d387c896e324afc9e676a901))
* add scenario test CLI ([8ff989a](https://github.com/chio-labs/sqlbuild/commit/8ff989a4bc98fbf095b39106bf6b73f88aec071e))
* add semantic cli style helper ([9f3e049](https://github.com/chio-labs/sqlbuild/commit/9f3e0495aa044777ef46f22900bf79634beba305))
* add skills update command ([e2546eb](https://github.com/chio-labs/sqlbuild/commit/e2546eb6b6d8963ba60c80d858612a861f667487))
* add snapshot materialization config skeleton ([c0f220e](https://github.com/chio-labs/sqlbuild/commit/c0f220ea20b7cebb338aefcaf4c392b9024c79cf))
* add source deferral for managed sources ([ad03aa8](https://github.com/chio-labs/sqlbuild/commit/ad03aa888f3f7da25187829abc044544a0c1a78d))
* add source freshness command ([a2d543d](https://github.com/chio-labs/sqlbuild/commit/a2d543d4efeab7df472c7d02385c7a75a6fa116f))
* add source freshness lag tolerance ([b657a84](https://github.com/chio-labs/sqlbuild/commit/b657a8453762e63677cc2a71acc57a9063704b12))
* add source freshness metadata foundation ([60d9d98](https://github.com/chio-labs/sqlbuild/commit/60d9d98a5ce90024014b7fbf13d06e3bd9fddb41))
* add source freshness state comparison ([77c70d9](https://github.com/chio-labs/sqlbuild/commit/77c70d90310ca399f346a8390089a7b0cf540b55))
* add source load command ([039ab0a](https://github.com/chio-labs/sqlbuild/commit/039ab0a9624fae8625eea60f817d9d2b64dc8523))
* add source loader dag execution ([96fa268](https://github.com/chio-labs/sqlbuild/commit/96fa268102c6907f3b5f93c220f047bf8b45f8fc))
* add source loader delete insert writes ([6aed601](https://github.com/chio-labs/sqlbuild/commit/6aed60105b966ba4f95f394cdeaf9f57ba059d98))
* add spinner based CLI progress ([9cce465](https://github.com/chio-labs/sqlbuild/commit/9cce465c454895bc79a35e9bee3cadbcd2ca34b3))
* add spinner based CLI progress ([9664cd9](https://github.com/chio-labs/sqlbuild/commit/9664cd9eb608819806cc2d7f9d59d57ecedbf987))
* add SQL unit test assertions ([640fbcb](https://github.com/chio-labs/sqlbuild/commit/640fbcb2fdcb090bba221524af32d665427a557e))
* add sqlglot cte parsing fallback ([a45c3ea](https://github.com/chio-labs/sqlbuild/commit/a45c3ea3b68ee184a1a6ce26f93b72f2fb2d4eff))
* add sqlserver adapter ([89086bc](https://github.com/chio-labs/sqlbuild/commit/89086bc49c4a91a0e7cdb18c332abf4df4a59603))
* add sqlserver adapter ([8eb0f87](https://github.com/chio-labs/sqlbuild/commit/8eb0f8729be77b00962789845a3b6cf1bfa3e54f))
* add static DAG JSON output ([1c8f497](https://github.com/chio-labs/sqlbuild/commit/1c8f49752bd72719ab3b5ff4e9c02b28fbcc1d1b))
* add structured execution diagnostics ([4bb1374](https://github.com/chio-labs/sqlbuild/commit/4bb13749c79fdc7a9c3cba86252f93bc2c4262a1))
* add table function SQL tests ([3b07fc6](https://github.com/chio-labs/sqlbuild/commit/3b07fc6fb61e3aae995c3cf7b6821600b1ec5b4d))
* add table function SQL tests ([8e8c1e4](https://github.com/chio-labs/sqlbuild/commit/8e8c1e4cbe28be4703dd51cd5bb938fab6e55b8a))
* add task and asset decorators ([c6dcfd5](https://github.com/chio-labs/sqlbuild/commit/c6dcfd5fa72473b15c1c3605125f6f037e441198))
* add UDF SQL test mode ([150b552](https://github.com/chio-labs/sqlbuild/commit/150b55225caab527a227f5568645b8e8a8437d2f))
* add UDF SQL test mode ([5738a42](https://github.com/chio-labs/sqlbuild/commit/5738a42c16d0041dffdb7c7ff5dedc16268d74e3))
* add unified python sql selector validation ([53ee19c](https://github.com/chio-labs/sqlbuild/commit/53ee19c2439e40c1a794be2da7431c463447d921))
* add versioned state foundation ([b9c16c3](https://github.com/chio-labs/sqlbuild/commit/b9c16c3b75b2957c3353d4ca7aceef3281aa4af9))
* add virtual build slice ([b6c74c9](https://github.com/chio-labs/sqlbuild/commit/b6c74c9cb6bda9918435929625092a3a15ad042d))
* add virtual clone hydration ([8f774ca](https://github.com/chio-labs/sqlbuild/commit/8f774ca73f2f0fc329b643c93916b1886662c1f0))
* add virtual diff promotion slice ([c44d42b](https://github.com/chio-labs/sqlbuild/commit/c44d42b45185f9cb8b4afcebd6bf873f21a0fd2e))
* add virtual planner slice ([668bbaf](https://github.com/chio-labs/sqlbuild/commit/668bbafa315d971dc0fc2cdb2c3fb46eb0d2f58e))
* add virtual playground template ([9aa01a4](https://github.com/chio-labs/sqlbuild/commit/9aa01a4d292faaf75059bb25aa4771eae5a7c948))
* add virtual playground template ([a4ce508](https://github.com/chio-labs/sqlbuild/commit/a4ce5088f62ea1ebe0f6077ebdfc8357f2edbf06))
* add virtual reconcile adopt detach ([ad63d06](https://github.com/chio-labs/sqlbuild/commit/ad63d06e58d9ad80895bf238d36b96fbf535ca0c))
* add virtual rollback checkpoints ([98b05dd](https://github.com/chio-labs/sqlbuild/commit/98b05dd58f59faa5c46c9436c05711aec75b80cb))
* add waffle shop playground ([a91f805](https://github.com/chio-labs/sqlbuild/commit/a91f805ac8a0eeaf5bf830a2dfdfe0d22c85f2e0))
* add warehouse zero copy clone support ([fef64e8](https://github.com/chio-labs/sqlbuild/commit/fef64e8dc1b2cda62c0419d793a1a7ec8cdfa030))
* align config and table function names ([b011ead](https://github.com/chio-labs/sqlbuild/commit/b011eadb0b9d3991dcdf53f522bb8d6f73682974))
* align config and table function names ([ec77895](https://github.com/chio-labs/sqlbuild/commit/ec7789511c095bd1d572a570e73a5a8e5867598d))
* align direct changes-only identity ([c3a4cd1](https://github.com/chio-labs/sqlbuild/commit/c3a4cd17623ff6dbb0b2e5283f41ab33152fb06e))
* allow scenario fixtures to sample sources ([a348eb9](https://github.com/chio-labs/sqlbuild/commit/a348eb99f82456d6203274a7785f46670d4aef40))
* allow scenario fixtures to sample sources ([cc363ca](https://github.com/chio-labs/sqlbuild/commit/cc363cad2bacdfc75b8e115682b574a226242866))
* apply direct source freshness changes-only ([5edf8e9](https://github.com/chio-labs/sqlbuild/commit/5edf8e90c477323de81ed73899e0ef716cca5a29))
* auto-load sources during builds ([58bc22c](https://github.com/chio-labs/sqlbuild/commit/58bc22c60f06cdc49c3a2932a4b282c2f567672c))
* batch source loader staging writes ([b28e22b](https://github.com/chio-labs/sqlbuild/commit/b28e22bd134a7b34f997bd74f916613a465570e4))
* bridge Dagster asset selections ([2e60398](https://github.com/chio-labs/sqlbuild/commit/2e603981c9ffc2aeab241645080fbbe41d68c3d3))
* build dbt combined graph ([a6ca203](https://github.com/chio-labs/sqlbuild/commit/a6ca203fd9b6f4aa989d3d059c0364048884fbc3))
* capture scenario snapshot column types ([208bb3f](https://github.com/chio-labs/sqlbuild/commit/208bb3f127a363ed75cc7f4a13dc18de883d4570))
* capture scenario snapshots ([7751286](https://github.com/chio-labs/sqlbuild/commit/7751286bc6b7c7397bdce3e5bae706b708f89dc4))
* clarify virtual function change causes ([fcd301d](https://github.com/chio-labs/sqlbuild/commit/fcd301de9a1303d36bc49b221ab2f7ea0bb12ac3))
* classify scenario snapshot state ([ebd9a8b](https://github.com/chio-labs/sqlbuild/commit/ebd9a8b8e80f4f6740b4052db9b3ef6560d0847d))
* clean direct fingerprint storage ([b0ead60](https://github.com/chio-labs/sqlbuild/commit/b0ead604b153c57fb50e4fd16dec0593c4d8b078))
* clean scenario artifacts ([2293a8a](https://github.com/chio-labs/sqlbuild/commit/2293a8a97098c3fa5a90ae7314dc06f1a89875bd))
* clean scenario artifacts with janitor ([19df620](https://github.com/chio-labs/sqlbuild/commit/19df620850dee53bf09724f91a3f3469d2468e13))
* color coded CLI errors ([e005632](https://github.com/chio-labs/sqlbuild/commit/e005632cfa13eeeebd49a708108893235bd290d5))
* complete loader context helpers ([66d7836](https://github.com/chio-labs/sqlbuild/commit/66d783603ef5ff6e4976a4f9f111cbd8eab665bf))
* complete PostgresAdapter with testcontainer tests and e2e coverage ([428405c](https://github.com/chio-labs/sqlbuild/commit/428405cc0f9a4292b22bcd361df1584ef76bf1f0))
* derive scenario snapshot inputs ([63afe4b](https://github.com/chio-labs/sqlbuild/commit/63afe4b1d508d810e30c5f860a6b0c2cad770bcf))
* discover check functions ([040aa55](https://github.com/chio-labs/sqlbuild/commit/040aa555710c662aa5173d776e6c20be041cb8f3))
* discover source loaders ([963fcf4](https://github.com/chio-labs/sqlbuild/commit/963fcf4ead4adae297cbe7a98b316a75a66d4d46))
* discover SQL scenarios ([d280dff](https://github.com/chio-labs/sqlbuild/commit/d280dff043714a7f48dc1b5de0c63291b06bdd68))
* discover task and asset functions ([bfde31f](https://github.com/chio-labs/sqlbuild/commit/bfde31fd6bb9408a82575859c25db11ce961207c))
* emit Dagster events from execution JSON ([4e5e1b6](https://github.com/chio-labs/sqlbuild/commit/4e5e1b62898a32a9a3d060f5b6f3aca38587ad8b))
* enforce model contract diagnostics ([c979856](https://github.com/chio-labs/sqlbuild/commit/c979856a2aa82f3e44b104028d37673f076daada))
* enforce selectable resource uniqueness ([3332c63](https://github.com/chio-labs/sqlbuild/commit/3332c63deb38e17809f65c9cd660834d06e28e77))
* enforce snapshot full refresh policy ([58a30e8](https://github.com/chio-labs/sqlbuild/commit/58a30e8e0af5d8198160dbf704c1ce912f37ed96))
* enforce source loader schema changes ([feb4820](https://github.com/chio-labs/sqlbuild/commit/feb4820ec182f6016c7c0e09f2a7d2b7fbf33bcd))
* enforce virtual source freshness skips ([278e753](https://github.com/chio-labs/sqlbuild/commit/278e75351fe3f262b52e66448016f4846ca622ed))
* execute check snapshot models ([0715946](https://github.com/chio-labs/sqlbuild/commit/07159465cfe2c4ff9f98fb27d92ea1d3a72324c2))
* execute dbt interop run and build ([91e80a5](https://github.com/chio-labs/sqlbuild/commit/91e80a5e10cc9e9c91533c61ae0c86e919c79b23))
* execute dbt interop tests ([cd3c556](https://github.com/chio-labs/sqlbuild/commit/cd3c55678db2df8d2500300ad3624575558f1e2b))
* execute historical check snapshots ([f1d49d6](https://github.com/chio-labs/sqlbuild/commit/f1d49d624943d4542dce975dac5f03b34d554370))
* execute historical timestamp change snapshots ([d955081](https://github.com/chio-labs/sqlbuild/commit/d95508157df6f41fa88ca5067ab2b4a7ebac1e5a))
* execute historical timestamp snapshots ([8044d9c](https://github.com/chio-labs/sqlbuild/commit/8044d9c9447996b190c22dced3be203c5d2b4c37))
* execute local scenario models ([102dc30](https://github.com/chio-labs/sqlbuild/commit/102dc30cbd420f900c9d97530af9839c74941061))
* execute python checks ([806c7f5](https://github.com/chio-labs/sqlbuild/commit/806c7f588246f2d34b78d42e775ce4284c6a8b5c))
* execute scenario checks ([a32ad16](https://github.com/chio-labs/sqlbuild/commit/a32ad16e2607fa02c6678c4582167c8ce0118cc0))
* execute scenario model graph ([8cba144](https://github.com/chio-labs/sqlbuild/commit/8cba1444d1fa3fd0dadcdae989a69fc810206960))
* execute timestamp snapshot models ([470b7aa](https://github.com/chio-labs/sqlbuild/commit/470b7aafe7380b61a6bed385f6ef1a43943c009b))
* expose loaders as dagster assets ([44bf2fc](https://github.com/chio-labs/sqlbuild/commit/44bf2fcf2346e51ff9d946f7226997a56ad39757))
* extract scenario CTE roles ([0ecbabf](https://github.com/chio-labs/sqlbuild/commit/0ecbabfba117c7eca1d3e4635e5117ac508f47b5))
* formalize adapter identity ([3977fad](https://github.com/chio-labs/sqlbuild/commit/3977fad13c39ab93c7d5dacda2c1074b1a5b62c5))
* generate SQLBuild skill from docs ([e1deb68](https://github.com/chio-labs/sqlbuild/commit/e1deb68df553feb9e1293b969e02679b212f6e3b))
* guard unsupported virtual commands ([68815b6](https://github.com/chio-labs/sqlbuild/commit/68815b6ce57bf120a4699b5ac9a9e0800540b302))
* guard virtual selection scopes ([b92bc10](https://github.com/chio-labs/sqlbuild/commit/b92bc1030e9d980b482cc37ae97fee7f74e889ba))
* handle snapshot schema changes ([64f160a](https://github.com/chio-labs/sqlbuild/commit/64f160a0a421f88fadea3871b0f070b9049f6bf0))
* harden cross-schema virtual moves ([ee7e1de](https://github.com/chio-labs/sqlbuild/commit/ee7e1de76ea2044edf11bc8989a850e8045d51ee))
* harden python build lifecycle ([d39df74](https://github.com/chio-labs/sqlbuild/commit/d39df7469fe29945b7059431f7bc330e277bcff6))
* harden versioned state core ([32dbae6](https://github.com/chio-labs/sqlbuild/commit/32dbae6d11fc1fe71e97e6a5139995bc14379b1c))
* harden virtual execution signatures ([75c4dc3](https://github.com/chio-labs/sqlbuild/commit/75c4dc354aa84520009c1f3a7e67db9b0f864d80))
* harden virtual janitor cleanup ([da58879](https://github.com/chio-labs/sqlbuild/commit/da588794601110aa935c80c0d29a7808f61280c3))
* harden virtual rollback checkpoints ([92ce8a5](https://github.com/chio-labs/sqlbuild/commit/92ce8a52d7302fa293857aa3f4623ab005936037))
* harden virtual state repair cleanup ([3f599dc](https://github.com/chio-labs/sqlbuild/commit/3f599dc8a16f26a36851abe2a7ecc417c09ab615))
* improve compile output ([8bb26f9](https://github.com/chio-labs/sqlbuild/commit/8bb26f97e5770895ea472dea27f06cda3d50ff9c))
* include python nodes in dag artifact ([18a9992](https://github.com/chio-labs/sqlbuild/commit/18a999253ba4ddf883387c95e2b073eb3bd9b8f6))
* include source freshness in virtual hashes ([952a18e](https://github.com/chio-labs/sqlbuild/commit/952a18e9bd3cd8c153232a707e811d59f2e7411f))
* infer scenario graph requirements ([555d545](https://github.com/chio-labs/sqlbuild/commit/555d54514cb6e0e4f664040c573901dcc0ed15b6))
* infer source loader row types ([a345d15](https://github.com/chio-labs/sqlbuild/commit/a345d151a0a3277b92c6fda988f25be93007027e))
* integrate python nodes with run lifecycle ([7f7bc17](https://github.com/chio-labs/sqlbuild/commit/7f7bc17d820739fa3acf3ddc05da65fb05dc4d97))
* integrate python nodes with virtual builds ([150b2c5](https://github.com/chio-labs/sqlbuild/commit/150b2c5f52697124c388528205c70bbb822e0473))
* invalidate historical snapshot hard deletes ([e2c148d](https://github.com/chio-labs/sqlbuild/commit/e2c148ddaa1706eada97a41377d833247b21484b))
* invalidate snapshot hard deletes ([9faa501](https://github.com/chio-labs/sqlbuild/commit/9faa501dc8ff1514eecf882255ef5de4cf7dd192))
* keep local scenario DuckDB runs ([91b8311](https://github.com/chio-labs/sqlbuild/commit/91b83111a41d1d892caec284917c81f5d07a888a))
* load local scenario snapshots ([eba3a7e](https://github.com/chio-labs/sqlbuild/commit/eba3a7e4f7a47d860f9106fe502d5e468b2044ef))
* load scenario project seeds ([0b52756](https://github.com/chio-labs/sqlbuild/commit/0b52756863816e7aa1d15af273619b607ea73293))
* make compile offline ([0099e0d](https://github.com/chio-labs/sqlbuild/commit/0099e0d61f458f68ba14b53531826a5ac77c9fa6))
* make compile offline ([eccb71a](https://github.com/chio-labs/sqlbuild/commit/eccb71a7bbd3a644c423f8c486e9f7f959272413))
* map python nodes in integrations ([3e5b324](https://github.com/chio-labs/sqlbuild/commit/3e5b3247763cf0389fdfb544fcf6fd9e224f0645))
* materialize scenario fixtures ([b49179a](https://github.com/chio-labs/sqlbuild/commit/b49179a2990aeb9b6cb7fe2c48bdd2c83b7a3784))
* mock dbt refs in tests and scenarios ([0bc7d40](https://github.com/chio-labs/sqlbuild/commit/0bc7d40e8e6649390b4dd7df969dfb0343ac3ce5))
* move source SQL rendering behind adapters ([3e57e0b](https://github.com/chio-labs/sqlbuild/commit/3e57e0bf9670de6e380c880a7ff66ab04550463b))
* name scenario artifacts ([93e0cb6](https://github.com/chio-labs/sqlbuild/commit/93e0cb6de5eddafbc6b7969fce90069ddba1d63f))
* observe direct source freshness during planning ([287ca9f](https://github.com/chio-labs/sqlbuild/commit/287ca9fa8dc226d7fa6c2766a20f97c6eaf6e9f1))
* orchestrate dbt interop plans ([92e8f39](https://github.com/chio-labs/sqlbuild/commit/92e8f39ae03f81e1b09c08c3aa463a6f61c7d042))
* orchestrate scenario capture steps ([1e9a21c](https://github.com/chio-labs/sqlbuild/commit/1e9a21cfcfbbf0855be21be033910e6f3a307527))
* persist virtual source freshness observations ([9bd6380](https://github.com/chio-labs/sqlbuild/commit/9bd6380f7cb0570da9e2d8045d90889d9a646252))
* persist virtual version metadata ([bc70ee0](https://github.com/chio-labs/sqlbuild/commit/bc70ee028c27eb2039599009a33add387e3bc5c6))
* plan scenario fixture SQL ([8fd0a69](https://github.com/chio-labs/sqlbuild/commit/8fd0a69e732d03620d4fa6cc2b50e83b77a8ceb0))
* plan scenario relation overrides ([1dfb94b](https://github.com/chio-labs/sqlbuild/commit/1dfb94bc8797cf0250f517eedc91015e7040306b))
* plan scenario snapshot capture ([dcbf3ae](https://github.com/chio-labs/sqlbuild/commit/dcbf3aee4616f627551bd356cf8197ff9c79f6fb))
* prune virtual checkpoints with janitor ([66cbd2c](https://github.com/chio-labs/sqlbuild/commit/66cbd2c842ae00a9b4efbce384892a4dcd7ca730))
* refine dbt plan output ([4090fa6](https://github.com/chio-labs/sqlbuild/commit/4090fa6a927e7fcf5dada88aa7e124c3d4ed11cd))
* refine plan section layout ([0ea662c](https://github.com/chio-labs/sqlbuild/commit/0ea662c410065efa8363949014668f19e31541c0))
* rename versioned mode to virtual ([a6da711](https://github.com/chio-labs/sqlbuild/commit/a6da711a0cc09a833809a63bd4db8c24246a1e36))
* require explicit path selector roots ([d4118ab](https://github.com/chio-labs/sqlbuild/commit/d4118aba4afac1d07eb23354df1ae2f742d567e4))
* resolve dbt interop selections ([87cdd3a](https://github.com/chio-labs/sqlbuild/commit/87cdd3a6c3b5f90ca3fdfa0b791be2dd1374234f))
* resolve dbt refs from manifest ([0ab4921](https://github.com/chio-labs/sqlbuild/commit/0ab49216ea0b43c2f293556132aa5074c9bd6ad7))
* route dbt interop arguments ([7fc4da3](https://github.com/chio-labs/sqlbuild/commit/7fc4da3aa2f615584c169a0781cf690ac31b1881))
* run local scenario functions ([906fc7e](https://github.com/chio-labs/sqlbuild/commit/906fc7e8071dd87c26e538e660cf102e7211c93b))
* scope rich column lineage ([521e47a](https://github.com/chio-labs/sqlbuild/commit/521e47adfde3f6cdb42cc8b5772553df4ca20e91))
* seed virtual model versions ([7e0f07f](https://github.com/chio-labs/sqlbuild/commit/7e0f07fc76223696c989109bffda0ba51bba8e18))
* select Dagster scenarios from assets ([6f584c8](https://github.com/chio-labs/sqlbuild/commit/6f584c83702689d90931006ba1bae19a5b2b1407))
* show nested SQL unit test checks ([b096564](https://github.com/chio-labs/sqlbuild/commit/b0965646820fc96e27e4576b37e9e25bf00f7eb8))
* show progress errors below rows ([cbe4a2a](https://github.com/chio-labs/sqlbuild/commit/cbe4a2a76232c0b854a369e5af02f5ebb0fbc5d8))
* show progress errors below rows ([4908b24](https://github.com/chio-labs/sqlbuild/commit/4908b24ef7e9d627d5c354dc5ebebdc255a38991))
* show python nodes in plan output ([abc278d](https://github.com/chio-labs/sqlbuild/commit/abc278d90d91d1b344408952f3ba922d4ac8df8f))
* stage source loader table writes ([5b2c9d6](https://github.com/chio-labs/sqlbuild/commit/5b2c9d6af09325e14e88c7f1ac5f8095a8a59ea8))
* stream SQLBuild output in Dagster ([b603449](https://github.com/chio-labs/sqlbuild/commit/b60344921fb88fb780239dc55aaf0d160b30a5f7))
* support adapter sqlglot dialect setting ([56926f3](https://github.com/chio-labs/sqlbuild/commit/56926f34bf8ad197f7c556355d87eead4a01f7fc))
* support direct changes-only pruning ([b746e1c](https://github.com/chio-labs/sqlbuild/commit/b746e1cf9fbac7f980dc59d25be37e773331c290))
* support explicit loader names ([9af93ea](https://github.com/chio-labs/sqlbuild/commit/9af93ea815c5a8a1f296a290ccc6d2be6332756b))
* support explicit loader names ([7add792](https://github.com/chio-labs/sqlbuild/commit/7add792c37525980f5fb5e8667c61ef653c04ea2))
* support hook context and CLI vars ([cb87357](https://github.com/chio-labs/sqlbuild/commit/cb873571f9bb574da5930ed2696d5b4b686c4849))
* support hook context and CLI vars ([b3fe1ab](https://github.com/chio-labs/sqlbuild/commit/b3fe1ab5a055054bd00b4a32ec32a079763bf651))
* support multiple scenario selectors ([270f872](https://github.com/chio-labs/sqlbuild/commit/270f872ae32ad84728aab16e8bf1725f4b520d86))
* support scenario select options ([bb64dd8](https://github.com/chio-labs/sqlbuild/commit/bb64dd84ffc328f6c85a73998db4a3f86803c2b4))
* support scenario select options ([e6a90a9](https://github.com/chio-labs/sqlbuild/commit/e6a90a9792962acb28cc95802e888ebdfff47405))
* support snapshot validity configuration ([b7fd384](https://github.com/chio-labs/sqlbuild/commit/b7fd3843f49c66e099af111221d608af1b3427ce))
* support virtual custom materializations ([c9a1447](https://github.com/chio-labs/sqlbuild/commit/c9a144788ad77b301c830856d917a177234f359d))
* support virtual custom materializations ([21bba32](https://github.com/chio-labs/sqlbuild/commit/21bba32086ca9ad5c175b7525679de76fced9752))
* support wildcard snapshot check columns ([90630f6](https://github.com/chio-labs/sqlbuild/commit/90630f630083d012ee39132d233c6c332f73c74c))
* sync local scenario snapshots ([fa428d4](https://github.com/chio-labs/sqlbuild/commit/fa428d43c3cc111c28cd551304a486bece13b024))
* tag SQLBuild Dagster asset kinds ([342bb61](https://github.com/chio-labs/sqlbuild/commit/342bb613dc022dd92f242a6035b1d2918ffd4926))
* tighten contract runtime diagnostics ([e051d44](https://github.com/chio-labs/sqlbuild/commit/e051d44663baf60b702578bb866499f0e43ad674))
* unify authored SQL interpolation ([c1d7e77](https://github.com/chio-labs/sqlbuild/commit/c1d7e77ec2545877949d59288d7c942afe031de3))
* unify CLI progress output ([0695eea](https://github.com/chio-labs/sqlbuild/commit/0695eeaca6b49e15152bead00e578c1f647c4936))
* validate contract config columns ([09311e7](https://github.com/chio-labs/sqlbuild/commit/09311e7ab4f69efe216c5ca66da9dde421354e8a))
* validate runtime model contracts ([b298ea1](https://github.com/chio-labs/sqlbuild/commit/b298ea1c858ac96f22280f894c95e53b5223e12d))
* validate source contract metadata ([ab906f2](https://github.com/chio-labs/sqlbuild/commit/ab906f2255ee7d2970a59aa05157035abc0aa435))
* validate upstream contract cursor inputs ([e244284](https://github.com/chio-labs/sqlbuild/commit/e2442845e551d0528af716bdb0834bf62a0ab308))
* version virtual functions ([33cea90](https://github.com/chio-labs/sqlbuild/commit/33cea909541ef442837259ca8dbfd13aa6ea56e5))
* wire dbt interop plan cli ([80d72d8](https://github.com/chio-labs/sqlbuild/commit/80d72d8e4fbb0b2ec85486b71840b27a050a02bf))
* write local scenario runtime artifacts ([64e5e4c](https://github.com/chio-labs/sqlbuild/commit/64e5e4c46509f197bed9074bed772e32f8294a02))
* write scenario runtime artifacts ([8add531](https://github.com/chio-labs/sqlbuild/commit/8add531783f03dc348368f6547e61da941f0ec16))


### Bug Fixes

* address reviewer feedback on postgres adapter coverage ([e1858bd](https://github.com/chio-labs/sqlbuild/commit/e1858bdcc1220a76861103c5c4acb5e4aaf501e1))
* align plan output columns ([8af7b74](https://github.com/chio-labs/sqlbuild/commit/8af7b740be77138b773fb44a4366a14bbad5d828))
* align snowflake loader identifiers ([aef8920](https://github.com/chio-labs/sqlbuild/commit/aef89209a78b88e468e700beb4a69352adb7a472))
* avoid stale diagnostics stderr handlers ([aa13c96](https://github.com/chio-labs/sqlbuild/commit/aa13c96d2658b2c2aac733d76aa56970ca889972))
* clarify snapshot refresh output ([ee2ebc5](https://github.com/chio-labs/sqlbuild/commit/ee2ebc56f2d46e24d3de228dbc188524c6a73153))
* clarify target rename cleanup ([8c3cd72](https://github.com/chio-labs/sqlbuild/commit/8c3cd720154934fc46805d75d2d75bc84d01c4f0))
* clarify virtual cli output ([386415a](https://github.com/chio-labs/sqlbuild/commit/386415a3b6678a5d6450b6ab19c2a02827c26ee6))
* clean up remaining rename fixtures ([b9c42c4](https://github.com/chio-labs/sqlbuild/commit/b9c42c4545f88946d1b7332037226c0ea60e71d5))
* clean up target rename fallout ([f3ed2be](https://github.com/chio-labs/sqlbuild/commit/f3ed2be5e1a226c6a2d6bf4acbe7c88ad909ef3e))
* configure databricks source deferral fixtures ([99c8540](https://github.com/chio-labs/sqlbuild/commit/99c85400245a2c3f3e00c0cb112cf5d0f8b42137))
* configure snowflake waffle source deferral ([31c64fc](https://github.com/chio-labs/sqlbuild/commit/31c64fc5550db211005c98043893b6991bde1745))
* default audit severity to error ([98f0dea](https://github.com/chio-labs/sqlbuild/commit/98f0dea12cdbc09c7ef5dbe58b79082985d5931d))
* default audit severity to error ([f9cf03f](https://github.com/chio-labs/sqlbuild/commit/f9cf03f88e00a581c74d3438c5e041bc621724ee))
* disambiguate source loader selection ([f79424a](https://github.com/chio-labs/sqlbuild/commit/f79424a01823be92d09810bbe62d5da18f10cd03))
* emit skill frontmatter before generated marker ([28c7a7c](https://github.com/chio-labs/sqlbuild/commit/28c7a7c8cdd2030552f7dae2eec1381a6e169c40))
* emit skill frontmatter before generated marker ([fc57032](https://github.com/chio-labs/sqlbuild/commit/fc57032d64eb6add883a00c6ef18633d5a6665e2))
* enforce python node factory folders ([ec2b7ac](https://github.com/chio-labs/sqlbuild/commit/ec2b7acf3e0eea237f209b394f9db1c4994fc602))
* enforce python node factory folders ([27117d6](https://github.com/chio-labs/sqlbuild/commit/27117d69e83dd5e63e73f796d5f02bf462796fcf))
* escape reference example calls ([bf8273f](https://github.com/chio-labs/sqlbuild/commit/bf8273fb9a9aec2997384d213ca6f4be37470fee))
* expose skip mode in public python APIs ([2019224](https://github.com/chio-labs/sqlbuild/commit/201922489477c1acfc242e13f89459d3f7d91601))
* expose skip mode in public python APIs ([403b4e4](https://github.com/chio-labs/sqlbuild/commit/403b4e46d8e2377ee94f20586b10cc110b193f06))
* gate virtual operations on state status ([a89f806](https://github.com/chio-labs/sqlbuild/commit/a89f8063a04c54174e67dcd0f812dae968cd01f1))
* gate virtual operations on state status ([c2edad2](https://github.com/chio-labs/sqlbuild/commit/c2edad2c79a9e3806d3294b234f35676271a03b8))
* group Dagster assets by SQLBuild project ([00c324f](https://github.com/chio-labs/sqlbuild/commit/00c324fa7feced8ae78c4fca98e89a2bfff8eccc))
* harden local scenario replay across adapters ([3aa655a](https://github.com/chio-labs/sqlbuild/commit/3aa655a9dbb86d17d4ddb76c53dd063062846ba1))
* harden soft and hard skip semantics ([f7459d3](https://github.com/chio-labs/sqlbuild/commit/f7459d3294d164eaf2044dec6eb6e52bd5a9e4c2))
* harden soft and hard skip semantics ([22db952](https://github.com/chio-labs/sqlbuild/commit/22db952587b41f1f7e2e4933cf02482088458d4f))
* harden source loader runtime ([a0c9f46](https://github.com/chio-labs/sqlbuild/commit/a0c9f469b312ba533a36232b2c11fd806bdad607))
* harden virtual promotion guards ([d33ce55](https://github.com/chio-labs/sqlbuild/commit/d33ce55712925f2c235c410f978918bc7baf7069))
* honor build start timestamp cursor override ([49b6396](https://github.com/chio-labs/sqlbuild/commit/49b639647cb543d21df423e0eee8074479622db4))
* honor build start timestamp cursor override ([99be657](https://github.com/chio-labs/sqlbuild/commit/99be65746f6c5dd274319383815247abc4ea1b84))
* improve Dagster demo and logging ([e120222](https://github.com/chio-labs/sqlbuild/commit/e12022213990de3c4fdf45708a0dfda8d8ddf157))
* include virtual table functions ([68d2781](https://github.com/chio-labs/sqlbuild/commit/68d278112d008f1ece4eae744ca507dd52ad8347))
* include virtual table functions ([b667184](https://github.com/chio-labs/sqlbuild/commit/b6671848990eb8a824faf2fe636197be26a08bd4))
* keep local replay error fixtures valid ([7f48d4c](https://github.com/chio-labs/sqlbuild/commit/7f48d4c48fdae80979bef3a2b2db943b06b74af5))
* keep playground install minimal ([e67a144](https://github.com/chio-labs/sqlbuild/commit/e67a14464c90653373eddd4bdfef46855802a6fc))
* make shared waffle fixture warehouse portable ([d8b84fa](https://github.com/chio-labs/sqlbuild/commit/d8b84fa64bf1c51950958c772b6bfc48d7c5c81d))
* make shared waffle fixture warehouse portable ([1ad677d](https://github.com/chio-labs/sqlbuild/commit/1ad677d47caa1fdb1fc7400e32004f724f285d9e))
* make sqlglot a core dependency ([a6e1517](https://github.com/chio-labs/sqlbuild/commit/a6e1517888e45cd4ddd8fdd1184f798bb7a27e69))
* make sqlglot a core dependency ([25119a7](https://github.com/chio-labs/sqlbuild/commit/25119a78d5b22841d680335b9e1e3f56991002d6))
* narrow function change fingerprints ([5bc5896](https://github.com/chio-labs/sqlbuild/commit/5bc58967bfa26e6330a78d4657f19a2bb4fd13ee))
* narrow function change fingerprints ([a0bf9bf](https://github.com/chio-labs/sqlbuild/commit/a0bf9bf4a020a84066078d798b9b9fc76af7b591))
* normalize path separators for Windows compatibility + add sqb init command ([0c95ecc](https://github.com/chio-labs/sqlbuild/commit/0c95eccf74534e74e53ada17d1673060873e5677))
* normalize path separators for Windows compatibility + init command ([75faf79](https://github.com/chio-labs/sqlbuild/commit/75faf796404f4277a92859ed1bfcbc5239bff39b))
* pass effective config to source loaders ([689f0df](https://github.com/chio-labs/sqlbuild/commit/689f0dff2d4d2fb7e4edd90b035c1428bf8e4d1f))
* place provider default target at top level ([a861c03](https://github.com/chio-labs/sqlbuild/commit/a861c03cf263db723f16d1ae1f2447805d23a588))
* polish scenario capture output ([f0ed8cb](https://github.com/chio-labs/sqlbuild/commit/f0ed8cbe48a3797513d8ea165931a02eb3d24bd7))
* polish virtual ops output ([e9a549a](https://github.com/chio-labs/sqlbuild/commit/e9a549ab4ec1dfe05903389f4561d029521602f1))
* polish virtual reconcile output ([f298ac9](https://github.com/chio-labs/sqlbuild/commit/f298ac9ec4bb6fb6b065cb693fb475c554033ee6))
* preserve managed source auto load expansion ([a3a8ba7](https://github.com/chio-labs/sqlbuild/commit/a3a8ba76d71546822bd06b615fffb0e049162285))
* preserve warehouse-specific test SQL behavior ([bce7b6c](https://github.com/chio-labs/sqlbuild/commit/bce7b6c87331c039d2d1a143eeb8b46cb95443b8))
* recognize dbt scenario artifacts ([c1f3274](https://github.com/chio-labs/sqlbuild/commit/c1f3274db1ef82aa78f597c97bd25063ea00f6b3))
* recognize dbt scenario artifacts ([6b8a5f5](https://github.com/chio-labs/sqlbuild/commit/6b8a5f542fbe19d4a824ba3a5b310f9ad840b808))
* reject dbt refs in audits ([e384ed1](https://github.com/chio-labs/sqlbuild/commit/e384ed185e31c2e0dbbccb826bed0b40f222240c))
* remove dbt mock fixture model ([e1c3a8d](https://github.com/chio-labs/sqlbuild/commit/e1c3a8da182bb0dce71c9917ad4d29fe19e1cc6a))
* render coded dbt interop errors ([12395a1](https://github.com/chio-labs/sqlbuild/commit/12395a19e7fbbb82971b814858cace906642f192))
* replace raw diagnostics with structured errors ([7a10cc6](https://github.com/chio-labs/sqlbuild/commit/7a10cc6602cc159144e42b14aea92d681ac6167d))
* require sqlglot for scenario snapshots ([7b6cf94](https://github.com/chio-labs/sqlbuild/commit/7b6cf94d4fbfad66581b0279909830aaabcf5f9a))
* resolve dbt interop paths absolutely ([c3a21ee](https://github.com/chio-labs/sqlbuild/commit/c3a21ee5e42ac9e9fe8fab79e6c0c08066a8862b))
* respect disabled sqlglot setting ([11ca558](https://github.com/chio-labs/sqlbuild/commit/11ca55858ac91a9be060f22b100fca4a938c80ac))
* respect local cascade policies ([d0b9c1d](https://github.com/chio-labs/sqlbuild/commit/d0b9c1db40cef4e4833c23e072240a1deef84beb))
* restore portable fingerprint ddl ([9fadc15](https://github.com/chio-labs/sqlbuild/commit/9fadc15ca4331197b7d4f6696c2399ce9703aaff))
* restore postgres real warehouse tests ([ad6f04a](https://github.com/chio-labs/sqlbuild/commit/ad6f04ab09c5208a98a2152cf860a0abde6dc4c5))
* run external loaders before warehouse connections ([b4427a4](https://github.com/chio-labs/sqlbuild/commit/b4427a4188f772b71011197ab87d25de52bdf932))
* run read-side check dependencies ([6e4e8f8](https://github.com/chio-labs/sqlbuild/commit/6e4e8f8a2ec92c284ed77709325550420397d219))
* run snapshot delta audits before mutation ([921b69c](https://github.com/chio-labs/sqlbuild/commit/921b69cb0a1d91a9d6aaf25a145f83e40a4b7343))
* scaffold all project resource directories ([2fefe84](https://github.com/chio-labs/sqlbuild/commit/2fefe845d66c5fd174aa08d0a20ab6ebedad836d))
* seed virtual versions lazily ([0b2d683](https://github.com/chio-labs/sqlbuild/commit/0b2d683105a7777f94a4fd20675601d98811e632))
* seed virtual versions lazily ([400c161](https://github.com/chio-labs/sqlbuild/commit/400c16109bd1bc1a805c9859083c628e10b160b1))
* show compile progress during builds ([e9838e8](https://github.com/chio-labs/sqlbuild/commit/e9838e8a38c8f3796d6d299f6f43a63b2654e0f6))
* stabilize python lifecycle selection ([fefca3f](https://github.com/chio-labs/sqlbuild/commit/fefca3f459ab7db87638e8e52b685c3b721d1c9e))
* stop ambient dbt manifest discovery ([9e35257](https://github.com/chio-labs/sqlbuild/commit/9e35257b0e12f2c68d8525d684d2f96ac179582b))
* suppress virtual fingerprint table writes ([7bae1eb](https://github.com/chio-labs/sqlbuild/commit/7bae1eb83f6dc5cd1dbd87843471b022847fdf56))
* validate source cursor input columns ([fb55504](https://github.com/chio-labs/sqlbuild/commit/fb55504913bff097819211eee53ab3c66184765b))


### Documentation

* add contributing guide and update logo ([4e3ce74](https://github.com/chio-labs/sqlbuild/commit/4e3ce748497d3eec80b85387f9f9e261ee715c30))
* clarify playground quick start ([75fa2c0](https://github.com/chio-labs/sqlbuild/commit/75fa2c0449fd96a241d29689c6d6d0b0b3cdb603))
* clarify playground quick start ([e0da66e](https://github.com/chio-labs/sqlbuild/commit/e0da66ee5203ea94585d1d81a2bb43c78702429c))
* document scenario local replay ([5a4577a](https://github.com/chio-labs/sqlbuild/commit/5a4577a2b527afd45a432a6a4e9536d1cad8ca6f))
* document source loaders ([65f3d6e](https://github.com/chio-labs/sqlbuild/commit/65f3d6e19cd68916c508238f22deb08b98597911))
* mention advanced virtual environments ([21b47ee](https://github.com/chio-labs/sqlbuild/commit/21b47ee5b3073780bf8e0c4fa5a09c57768fa972))
* refresh sqlbuild skill ([52a28a6](https://github.com/chio-labs/sqlbuild/commit/52a28a69919a2183ed4afbae86edd347babe072a))
* trim scenario selector note ([34bc6e9](https://github.com/chio-labs/sqlbuild/commit/34bc6e917b71521ab257f82a35f0df3f9c8942b6))
* update generated sqlbuild skill ([0d1f18a](https://github.com/chio-labs/sqlbuild/commit/0d1f18ac2abd563aab9fa7257436947b6be1510c))
* update README assertion example ([34de007](https://github.com/chio-labs/sqlbuild/commit/34de00739f28fca41237c80f3b13ce8a3dff6c56))
* update README assertion example ([1bbd600](https://github.com/chio-labs/sqlbuild/commit/1bbd600d3bd7f62220a03e68111a4fa3e1bed9aa))
* update README source names ([f2041b7](https://github.com/chio-labs/sqlbuild/commit/f2041b78b544ecdd4e8a17139cf9d69b28be2551))
* use absolute readme logo url ([a5b5d2c](https://github.com/chio-labs/sqlbuild/commit/a5b5d2c8003aa41125752a084b36865e6d7e62bc))
* use relative README logo path ([0203ad8](https://github.com/chio-labs/sqlbuild/commit/0203ad8ca827f8d9c23309432601ce27b27b4b82))

## [0.28.0](https://github.com/chio-labs/sqlbuild/compare/v0.27.0...v0.28.0) (2026-06-06)


### Features

* add source freshness command ([a2d543d](https://github.com/chio-labs/sqlbuild/commit/a2d543d4efeab7df472c7d02385c7a75a6fa116f))
* add source freshness state comparison ([77c70d9](https://github.com/chio-labs/sqlbuild/commit/77c70d90310ca399f346a8390089a7b0cf540b55))


### Bug Fixes

* place provider default target at top level ([a861c03](https://github.com/chio-labs/sqlbuild/commit/a861c03cf263db723f16d1ae1f2447805d23a588))

## [0.27.0](https://github.com/chio-labs/sqlbuild/compare/v0.26.2...v0.27.0) (2026-06-03)


### Features

* add bigquery and databricks freshness metadata ([875796d](https://github.com/chio-labs/sqlbuild/commit/875796d1990dda1ec590854a6367d0af4660b85b))
* add source freshness metadata foundation ([60d9d98](https://github.com/chio-labs/sqlbuild/commit/60d9d98a5ce90024014b7fbf13d06e3bd9fddb41))
* enforce virtual source freshness skips ([278e753](https://github.com/chio-labs/sqlbuild/commit/278e75351fe3f262b52e66448016f4846ca622ed))
* harden virtual execution signatures ([75c4dc3](https://github.com/chio-labs/sqlbuild/commit/75c4dc354aa84520009c1f3a7e67db9b0f864d80))
* include source freshness in virtual hashes ([952a18e](https://github.com/chio-labs/sqlbuild/commit/952a18e9bd3cd8c153232a707e811d59f2e7411f))
* persist virtual source freshness observations ([9bd6380](https://github.com/chio-labs/sqlbuild/commit/9bd6380f7cb0570da9e2d8045d90889d9a646252))


### Bug Fixes

* run read-side check dependencies ([6e4e8f8](https://github.com/chio-labs/sqlbuild/commit/6e4e8f8a2ec92c284ed77709325550420397d219))

## [0.26.2](https://github.com/chio-labs/sqlbuild/compare/v0.26.1...v0.26.2) (2026-06-03)


### Bug Fixes

* harden soft and hard skip semantics ([f7459d3](https://github.com/chio-labs/sqlbuild/commit/f7459d3294d164eaf2044dec6eb6e52bd5a9e4c2))
* harden soft and hard skip semantics ([22db952](https://github.com/chio-labs/sqlbuild/commit/22db952587b41f1f7e2e4933cf02482088458d4f))

## [0.26.1](https://github.com/chio-labs/sqlbuild/compare/v0.26.0...v0.26.1) (2026-06-02)


### Bug Fixes

* enforce python node factory folders ([ec2b7ac](https://github.com/chio-labs/sqlbuild/commit/ec2b7acf3e0eea237f209b394f9db1c4994fc602))
* enforce python node factory folders ([27117d6](https://github.com/chio-labs/sqlbuild/commit/27117d69e83dd5e63e73f796d5f02bf462796fcf))

## [0.26.0](https://github.com/chio-labs/sqlbuild/compare/v0.25.1...v0.26.0) (2026-06-02)


### Features

* add python node factories ([ba64a5d](https://github.com/chio-labs/sqlbuild/commit/ba64a5dcc221bcf6d106b4dd69bd97d352696476))
* add python node factories ([7386f73](https://github.com/chio-labs/sqlbuild/commit/7386f7392d98317b1f464044541218409bb0fa82))
* support explicit loader names ([9af93ea](https://github.com/chio-labs/sqlbuild/commit/9af93ea815c5a8a1f296a290ccc6d2be6332756b))


### Bug Fixes

* clarify target rename cleanup ([8c3cd72](https://github.com/chio-labs/sqlbuild/commit/8c3cd720154934fc46805d75d2d75bc84d01c4f0))
* clean up remaining rename fixtures ([b9c42c4](https://github.com/chio-labs/sqlbuild/commit/b9c42c4545f88946d1b7332037226c0ea60e71d5))
* clean up target rename fallout ([f3ed2be](https://github.com/chio-labs/sqlbuild/commit/f3ed2be5e1a226c6a2d6bf4acbe7c88ad909ef3e))

## [0.25.1](https://github.com/chio-labs/sqlbuild/compare/v0.25.0...v0.25.1) (2026-06-01)


### Bug Fixes

* expose skip mode in public python APIs ([2019224](https://github.com/chio-labs/sqlbuild/commit/201922489477c1acfc242e13f89459d3f7d91601))
* expose skip mode in public python APIs ([403b4e4](https://github.com/chio-labs/sqlbuild/commit/403b4e46d8e2377ee94f20586b10cc110b193f06))

## [0.25.0](https://github.com/chio-labs/sqlbuild/compare/v0.24.0...v0.25.0) (2026-06-01)


### Features

* add cli document helper ([bbbb2cb](https://github.com/chio-labs/sqlbuild/commit/bbbb2cbf35e407b6899052723f7cdaac5c331918))
* add python check result context ([8542fcc](https://github.com/chio-labs/sqlbuild/commit/8542fcc270063f4dc9eb0d591f2438ffbc6bd30c))
* add python node contexts ([00536e7](https://github.com/chio-labs/sqlbuild/commit/00536e73330bb7abbcf85035062164fc2e640841))
* add python node executor ([4bed0fb](https://github.com/chio-labs/sqlbuild/commit/4bed0fba89e9b3c9aade7483aa3818f8b99eaf3a))
* add python node foundation ([6f0a20f](https://github.com/chio-labs/sqlbuild/commit/6f0a20f67bef9f33dd735b133daba660f51ef5c7))
* add python node graph inventory ([e8ffa75](https://github.com/chio-labs/sqlbuild/commit/e8ffa75aa457220d092f91049879cae005e5d854))
* add python node result policies ([dec97fe](https://github.com/chio-labs/sqlbuild/commit/dec97fed017095d20f4f043393cff5f6d8405d5d))
* add python node retry policy ([ba2303a](https://github.com/chio-labs/sqlbuild/commit/ba2303a3bfe29e7b0c1e54516848dee1c4f80aa5))
* add python node selector resolver ([3bd4339](https://github.com/chio-labs/sqlbuild/commit/3bd433961a9e4141ae971465860d3c531002b841))
* add python nodes playground ([f6114b1](https://github.com/chio-labs/sqlbuild/commit/f6114b19bde901aa87e8a735619649772eea95d3))
* add semantic cli style helper ([9f3e049](https://github.com/chio-labs/sqlbuild/commit/9f3e0495aa044777ef46f22900bf79634beba305))
* add task and asset decorators ([c6dcfd5](https://github.com/chio-labs/sqlbuild/commit/c6dcfd5fa72473b15c1c3605125f6f037e441198))
* add unified python sql selector validation ([53ee19c](https://github.com/chio-labs/sqlbuild/commit/53ee19c2439e40c1a794be2da7431c463447d921))
* discover check functions ([040aa55](https://github.com/chio-labs/sqlbuild/commit/040aa555710c662aa5173d776e6c20be041cb8f3))
* discover task and asset functions ([bfde31f](https://github.com/chio-labs/sqlbuild/commit/bfde31fd6bb9408a82575859c25db11ce961207c))
* enforce selectable resource uniqueness ([3332c63](https://github.com/chio-labs/sqlbuild/commit/3332c63deb38e17809f65c9cd660834d06e28e77))
* execute python checks ([806c7f5](https://github.com/chio-labs/sqlbuild/commit/806c7f588246f2d34b78d42e775ce4284c6a8b5c))
* harden python build lifecycle ([d39df74](https://github.com/chio-labs/sqlbuild/commit/d39df7469fe29945b7059431f7bc330e277bcff6))
* include python nodes in dag artifact ([18a9992](https://github.com/chio-labs/sqlbuild/commit/18a999253ba4ddf883387c95e2b073eb3bd9b8f6))
* integrate python nodes with run lifecycle ([7f7bc17](https://github.com/chio-labs/sqlbuild/commit/7f7bc17d820739fa3acf3ddc05da65fb05dc4d97))
* integrate python nodes with virtual builds ([150b2c5](https://github.com/chio-labs/sqlbuild/commit/150b2c5f52697124c388528205c70bbb822e0473))
* map python nodes in integrations ([3e5b324](https://github.com/chio-labs/sqlbuild/commit/3e5b3247763cf0389fdfb544fcf6fd9e224f0645))
* require explicit path selector roots ([d4118ab](https://github.com/chio-labs/sqlbuild/commit/d4118aba4afac1d07eb23354df1ae2f742d567e4))
* show python nodes in plan output ([abc278d](https://github.com/chio-labs/sqlbuild/commit/abc278d90d91d1b344408952f3ba922d4ac8df8f))


### Bug Fixes

* avoid stale diagnostics stderr handlers ([aa13c96](https://github.com/chio-labs/sqlbuild/commit/aa13c96d2658b2c2aac733d76aa56970ca889972))
* preserve managed source auto load expansion ([a3a8ba7](https://github.com/chio-labs/sqlbuild/commit/a3a8ba76d71546822bd06b615fffb0e049162285))
* show compile progress during builds ([e9838e8](https://github.com/chio-labs/sqlbuild/commit/e9838e8a38c8f3796d6d299f6f43a63b2654e0f6))
* stabilize python lifecycle selection ([fefca3f](https://github.com/chio-labs/sqlbuild/commit/fefca3f459ab7db87638e8e52b685c3b721d1c9e))

## [0.24.0](https://github.com/chio-labs/sqlbuild/compare/v0.23.0...v0.24.0) (2026-05-28)


### Features

* add rivers integration ([82de30c](https://github.com/chio-labs/sqlbuild/commit/82de30ca29f4cde1deba35f08d6575fa82657c62))
* add rivers integration ([9268beb](https://github.com/chio-labs/sqlbuild/commit/9268beb1cae3bd78f51f9e17241767c892d51722))

## [0.23.0](https://github.com/chio-labs/sqlbuild/compare/v0.22.1...v0.23.0) (2026-05-28)


### Features

* support virtual custom materializations ([c9a1447](https://github.com/chio-labs/sqlbuild/commit/c9a144788ad77b301c830856d917a177234f359d))
* support virtual custom materializations ([21bba32](https://github.com/chio-labs/sqlbuild/commit/21bba32086ca9ad5c175b7525679de76fced9752))


### Bug Fixes

* include virtual table functions ([68d2781](https://github.com/chio-labs/sqlbuild/commit/68d278112d008f1ece4eae744ca507dd52ad8347))
* include virtual table functions ([b667184](https://github.com/chio-labs/sqlbuild/commit/b6671848990eb8a824faf2fe636197be26a08bd4))
* seed virtual versions lazily ([0b2d683](https://github.com/chio-labs/sqlbuild/commit/0b2d683105a7777f94a4fd20675601d98811e632))
* seed virtual versions lazily ([400c161](https://github.com/chio-labs/sqlbuild/commit/400c16109bd1bc1a805c9859083c628e10b160b1))

## [0.22.1](https://github.com/chio-labs/sqlbuild/compare/v0.22.0...v0.22.1) (2026-05-28)


### Bug Fixes

* gate virtual operations on state status ([a89f806](https://github.com/chio-labs/sqlbuild/commit/a89f8063a04c54174e67dcd0f812dae968cd01f1))
* gate virtual operations on state status ([c2edad2](https://github.com/chio-labs/sqlbuild/commit/c2edad2c79a9e3806d3294b234f35676271a03b8))

## [0.22.0](https://github.com/chio-labs/sqlbuild/compare/v0.21.0...v0.22.0) (2026-05-28)


### Features

* add virtual playground template ([9aa01a4](https://github.com/chio-labs/sqlbuild/commit/9aa01a4d292faaf75059bb25aa4771eae5a7c948))
* add virtual playground template ([a4ce508](https://github.com/chio-labs/sqlbuild/commit/a4ce5088f62ea1ebe0f6077ebdfc8357f2edbf06))

## [0.21.0](https://github.com/chio-labs/sqlbuild/compare/v0.20.1...v0.21.0) (2026-05-28)


### Features

* add virtual reconcile adopt detach ([ad63d06](https://github.com/chio-labs/sqlbuild/commit/ad63d06e58d9ad80895bf238d36b96fbf535ca0c))
* harden cross-schema virtual moves ([ee7e1de](https://github.com/chio-labs/sqlbuild/commit/ee7e1de76ea2044edf11bc8989a850e8045d51ee))
* harden virtual janitor cleanup ([da58879](https://github.com/chio-labs/sqlbuild/commit/da588794601110aa935c80c0d29a7808f61280c3))
* harden virtual rollback checkpoints ([92ce8a5](https://github.com/chio-labs/sqlbuild/commit/92ce8a52d7302fa293857aa3f4623ab005936037))
* harden virtual state repair cleanup ([3f599dc](https://github.com/chio-labs/sqlbuild/commit/3f599dc8a16f26a36851abe2a7ecc417c09ab615))
* prune virtual checkpoints with janitor ([66cbd2c](https://github.com/chio-labs/sqlbuild/commit/66cbd2c842ae00a9b4efbce384892a4dcd7ca730))
* seed virtual model versions ([7e0f07f](https://github.com/chio-labs/sqlbuild/commit/7e0f07fc76223696c989109bffda0ba51bba8e18))
* version virtual functions ([33cea90](https://github.com/chio-labs/sqlbuild/commit/33cea909541ef442837259ca8dbfd13aa6ea56e5))


### Bug Fixes

* polish virtual ops output ([e9a549a](https://github.com/chio-labs/sqlbuild/commit/e9a549ab4ec1dfe05903389f4561d029521602f1))
* polish virtual reconcile output ([f298ac9](https://github.com/chio-labs/sqlbuild/commit/f298ac9ec4bb6fb6b065cb693fb475c554033ee6))
* suppress virtual fingerprint table writes ([7bae1eb](https://github.com/chio-labs/sqlbuild/commit/7bae1eb83f6dc5cd1dbd87843471b022847fdf56))


### Documentation

* mention advanced virtual environments ([21b47ee](https://github.com/chio-labs/sqlbuild/commit/21b47ee5b3073780bf8e0c4fa5a09c57768fa972))
* trim scenario selector note ([34bc6e9](https://github.com/chio-labs/sqlbuild/commit/34bc6e917b71521ab257f82a35f0df3f9c8942b6))

## [0.20.1](https://github.com/chio-labs/sqlbuild/compare/v0.20.0...v0.20.1) (2026-05-26)


### Bug Fixes

* make sqlglot a core dependency ([a6e1517](https://github.com/chio-labs/sqlbuild/commit/a6e1517888e45cd4ddd8fdd1184f798bb7a27e69))
* make sqlglot a core dependency ([25119a7](https://github.com/chio-labs/sqlbuild/commit/25119a78d5b22841d680335b9e1e3f56991002d6))
* scaffold all project resource directories ([2fefe84](https://github.com/chio-labs/sqlbuild/commit/2fefe845d66c5fd174aa08d0a20ab6ebedad836d))

## [0.20.0](https://github.com/chio-labs/sqlbuild/compare/v0.19.0...v0.20.0) (2026-05-26)


### Features

* support scenario select options ([bb64dd8](https://github.com/chio-labs/sqlbuild/commit/bb64dd84ffc328f6c85a73998db4a3f86803c2b4))
* support scenario select options ([e6a90a9](https://github.com/chio-labs/sqlbuild/commit/e6a90a9792962acb28cc95802e888ebdfff47405))


### Bug Fixes

* honor build start timestamp cursor override ([49b6396](https://github.com/chio-labs/sqlbuild/commit/49b639647cb543d21df423e0eee8074479622db4))
* honor build start timestamp cursor override ([99be657](https://github.com/chio-labs/sqlbuild/commit/99be65746f6c5dd274319383815247abc4ea1b84))
* normalize path separators for Windows compatibility + add sqb init command ([0c95ecc](https://github.com/chio-labs/sqlbuild/commit/0c95eccf74534e74e53ada17d1673060873e5677))
* normalize path separators for Windows compatibility + init command ([75faf79](https://github.com/chio-labs/sqlbuild/commit/75faf796404f4277a92859ed1bfcbc5239bff39b))

## [0.19.0](https://github.com/chio-labs/sqlbuild/compare/v0.18.0...v0.19.0) (2026-05-24)


### Features

* add ingestr integration loaders ([d824860](https://github.com/chio-labs/sqlbuild/commit/d824860cb186b9a069e42c629b3680180fdd0552))
* formalize adapter identity ([3977fad](https://github.com/chio-labs/sqlbuild/commit/3977fad13c39ab93c7d5dacda2c1074b1a5b62c5))


### Bug Fixes

* run external loaders before warehouse connections ([b4427a4](https://github.com/chio-labs/sqlbuild/commit/b4427a4188f772b71011197ab87d25de52bdf932))

## [0.18.0](https://github.com/chio-labs/sqlbuild/compare/v0.17.0...v0.18.0) (2026-05-23)


### Features

* add sqlserver adapter ([89086bc](https://github.com/chio-labs/sqlbuild/commit/89086bc49c4a91a0e7cdb18c332abf4df4a59603))
* add sqlserver adapter ([8eb0f87](https://github.com/chio-labs/sqlbuild/commit/8eb0f8729be77b00962789845a3b6cf1bfa3e54f))
* expose loaders as dagster assets ([44bf2fc](https://github.com/chio-labs/sqlbuild/commit/44bf2fcf2346e51ff9d946f7226997a56ad39757))


### Bug Fixes

* align snowflake loader identifiers ([aef8920](https://github.com/chio-labs/sqlbuild/commit/aef89209a78b88e468e700beb4a69352adb7a472))
* configure databricks source deferral fixtures ([99c8540](https://github.com/chio-labs/sqlbuild/commit/99c85400245a2c3f3e00c0cb112cf5d0f8b42137))
* configure snowflake waffle source deferral ([31c64fc](https://github.com/chio-labs/sqlbuild/commit/31c64fc5550db211005c98043893b6991bde1745))
* restore portable fingerprint ddl ([9fadc15](https://github.com/chio-labs/sqlbuild/commit/9fadc15ca4331197b7d4f6696c2399ce9703aaff))
* restore postgres real warehouse tests ([ad6f04a](https://github.com/chio-labs/sqlbuild/commit/ad6f04ab09c5208a98a2152cf860a0abde6dc4c5))


### Documentation

* document source loaders ([65f3d6e](https://github.com/chio-labs/sqlbuild/commit/65f3d6e19cd68916c508238f22deb08b98597911))
* refresh sqlbuild skill ([52a28a6](https://github.com/chio-labs/sqlbuild/commit/52a28a69919a2183ed4afbae86edd347babe072a))

## [0.17.0](https://github.com/chio-labs/sqlbuild/compare/v0.16.2...v0.17.0) (2026-05-23)


### Features

* add concurrent load and seed execution ([0efa072](https://github.com/chio-labs/sqlbuild/commit/0efa072d3193a5f9ff3503ad25b11ef41aa2421b))
* add concurrent loader dag scheduling ([2bb66e9](https://github.com/chio-labs/sqlbuild/commit/2bb66e976d040ba481ea75eb7aea78ff25cf1c77))
* add incremental source loader writes ([d4a598b](https://github.com/chio-labs/sqlbuild/commit/d4a598bbe316f4f4d1132ffc0e2a20bb46067029))
* add loader cursor override context ([44abb1b](https://github.com/chio-labs/sqlbuild/commit/44abb1b9af224153011bc78fb8fa6ebd4374cd2e))
* add source deferral for managed sources ([ad03aa8](https://github.com/chio-labs/sqlbuild/commit/ad03aa888f3f7da25187829abc044544a0c1a78d))
* add source load command ([039ab0a](https://github.com/chio-labs/sqlbuild/commit/039ab0a9624fae8625eea60f817d9d2b64dc8523))
* add source loader dag execution ([96fa268](https://github.com/chio-labs/sqlbuild/commit/96fa268102c6907f3b5f93c220f047bf8b45f8fc))
* add source loader delete insert writes ([6aed601](https://github.com/chio-labs/sqlbuild/commit/6aed60105b966ba4f95f394cdeaf9f57ba059d98))
* auto-load sources during builds ([58bc22c](https://github.com/chio-labs/sqlbuild/commit/58bc22c60f06cdc49c3a2932a4b282c2f567672c))
* batch source loader staging writes ([b28e22b](https://github.com/chio-labs/sqlbuild/commit/b28e22bd134a7b34f997bd74f916613a465570e4))
* complete loader context helpers ([66d7836](https://github.com/chio-labs/sqlbuild/commit/66d783603ef5ff6e4976a4f9f111cbd8eab665bf))
* discover source loaders ([963fcf4](https://github.com/chio-labs/sqlbuild/commit/963fcf4ead4adae297cbe7a98b316a75a66d4d46))
* enforce source loader schema changes ([feb4820](https://github.com/chio-labs/sqlbuild/commit/feb4820ec182f6016c7c0e09f2a7d2b7fbf33bcd))
* infer source loader row types ([a345d15](https://github.com/chio-labs/sqlbuild/commit/a345d151a0a3277b92c6fda988f25be93007027e))
* move source SQL rendering behind adapters ([3e57e0b](https://github.com/chio-labs/sqlbuild/commit/3e57e0bf9670de6e380c880a7ff66ab04550463b))
* stage source loader table writes ([5b2c9d6](https://github.com/chio-labs/sqlbuild/commit/5b2c9d6af09325e14e88c7f1ac5f8095a8a59ea8))


### Bug Fixes

* disambiguate source loader selection ([f79424a](https://github.com/chio-labs/sqlbuild/commit/f79424a01823be92d09810bbe62d5da18f10cd03))
* harden source loader runtime ([a0c9f46](https://github.com/chio-labs/sqlbuild/commit/a0c9f469b312ba533a36232b2c11fd806bdad607))
* pass effective config to source loaders ([689f0df](https://github.com/chio-labs/sqlbuild/commit/689f0dff2d4d2fb7e4edd90b035c1428bf8e4d1f))

## [0.16.2](https://github.com/chio-labs/sqlbuild/compare/v0.16.1...v0.16.2) (2026-05-18)


### Documentation

* update README assertion example ([34de007](https://github.com/chio-labs/sqlbuild/commit/34de00739f28fca41237c80f3b13ce8a3dff6c56))
* update README assertion example ([1bbd600](https://github.com/chio-labs/sqlbuild/commit/1bbd600d3bd7f62220a03e68111a4fa3e1bed9aa))

## [0.16.1](https://github.com/chio-labs/sqlbuild/compare/v0.16.0...v0.16.1) (2026-05-17)


### Bug Fixes

* emit skill frontmatter before generated marker ([28c7a7c](https://github.com/chio-labs/sqlbuild/commit/28c7a7c8cdd2030552f7dae2eec1381a6e169c40))
* emit skill frontmatter before generated marker ([fc57032](https://github.com/chio-labs/sqlbuild/commit/fc57032d64eb6add883a00c6ef18633d5a6665e2))

## [0.16.0](https://github.com/chio-labs/sqlbuild/compare/v0.15.0...v0.16.0) (2026-05-17)


### Features

* add MotherDuck adapter ([403d536](https://github.com/chio-labs/sqlbuild/commit/403d536c0af1a65ed793d3dc6744fb923c32e1a3))
* add MotherDuck adapter ([36b70ef](https://github.com/chio-labs/sqlbuild/commit/36b70ef0746954db09a6755e79dd9d1ba585f947))
* add PostgreSQL adapter ([2b7b1c5](https://github.com/chio-labs/sqlbuild/commit/2b7b1c5822a75eda23ab1610541ce8cdcb998802))
* complete PostgresAdapter with testcontainer tests and e2e coverage ([428405c](https://github.com/chio-labs/sqlbuild/commit/428405cc0f9a4292b22bcd361df1584ef76bf1f0))


### Bug Fixes

* address reviewer feedback on postgres adapter coverage ([e1858bd](https://github.com/chio-labs/sqlbuild/commit/e1858bdcc1220a76861103c5c4acb5e4aaf501e1))
* make shared waffle fixture warehouse portable ([d8b84fa](https://github.com/chio-labs/sqlbuild/commit/d8b84fa64bf1c51950958c772b6bfc48d7c5c81d))
* make shared waffle fixture warehouse portable ([1ad677d](https://github.com/chio-labs/sqlbuild/commit/1ad677d47caa1fdb1fc7400e32004f724f285d9e))

## [0.15.0](https://github.com/chio-labs/sqlbuild/compare/v0.14.0...v0.15.0) (2026-05-17)


### Features

* add structured execution diagnostics ([4bb1374](https://github.com/chio-labs/sqlbuild/commit/4bb13749c79fdc7a9c3cba86252f93bc2c4262a1))
* tighten contract runtime diagnostics ([e051d44](https://github.com/chio-labs/sqlbuild/commit/e051d44663baf60b702578bb866499f0e43ad674))
* validate runtime model contracts ([b298ea1](https://github.com/chio-labs/sqlbuild/commit/b298ea1c858ac96f22280f894c95e53b5223e12d))
* validate source contract metadata ([ab906f2](https://github.com/chio-labs/sqlbuild/commit/ab906f2255ee7d2970a59aa05157035abc0aa435))


### Bug Fixes

* replace raw diagnostics with structured errors ([7a10cc6](https://github.com/chio-labs/sqlbuild/commit/7a10cc6602cc159144e42b14aea92d681ac6167d))


### Documentation

* update generated sqlbuild skill ([0d1f18a](https://github.com/chio-labs/sqlbuild/commit/0d1f18ac2abd563aab9fa7257436947b6be1510c))

## [0.14.0](https://github.com/chio-labs/sqlbuild/compare/v0.13.0...v0.14.0) (2026-05-16)


### Features

* add snapshot materialization config skeleton ([c0f220e](https://github.com/chio-labs/sqlbuild/commit/c0f220ea20b7cebb338aefcaf4c392b9024c79cf))
* enforce snapshot full refresh policy ([58a30e8](https://github.com/chio-labs/sqlbuild/commit/58a30e8e0af5d8198160dbf704c1ce912f37ed96))
* execute check snapshot models ([0715946](https://github.com/chio-labs/sqlbuild/commit/07159465cfe2c4ff9f98fb27d92ea1d3a72324c2))
* execute historical check snapshots ([f1d49d6](https://github.com/chio-labs/sqlbuild/commit/f1d49d624943d4542dce975dac5f03b34d554370))
* execute historical timestamp change snapshots ([d955081](https://github.com/chio-labs/sqlbuild/commit/d95508157df6f41fa88ca5067ab2b4a7ebac1e5a))
* execute historical timestamp snapshots ([8044d9c](https://github.com/chio-labs/sqlbuild/commit/8044d9c9447996b190c22dced3be203c5d2b4c37))
* execute timestamp snapshot models ([470b7aa](https://github.com/chio-labs/sqlbuild/commit/470b7aafe7380b61a6bed385f6ef1a43943c009b))
* handle snapshot schema changes ([64f160a](https://github.com/chio-labs/sqlbuild/commit/64f160a0a421f88fadea3871b0f070b9049f6bf0))
* invalidate historical snapshot hard deletes ([e2c148d](https://github.com/chio-labs/sqlbuild/commit/e2c148ddaa1706eada97a41377d833247b21484b))
* invalidate snapshot hard deletes ([9faa501](https://github.com/chio-labs/sqlbuild/commit/9faa501dc8ff1514eecf882255ef5de4cf7dd192))
* support snapshot validity configuration ([b7fd384](https://github.com/chio-labs/sqlbuild/commit/b7fd3843f49c66e099af111221d608af1b3427ce))
* support wildcard snapshot check columns ([90630f6](https://github.com/chio-labs/sqlbuild/commit/90630f630083d012ee39132d233c6c332f73c74c))


### Bug Fixes

* preserve warehouse-specific test SQL behavior ([bce7b6c](https://github.com/chio-labs/sqlbuild/commit/bce7b6c87331c039d2d1a143eeb8b46cb95443b8))
* run snapshot delta audits before mutation ([921b69c](https://github.com/chio-labs/sqlbuild/commit/921b69cb0a1d91a9d6aaf25a145f83e40a4b7343))
* validate source cursor input columns ([fb55504](https://github.com/chio-labs/sqlbuild/commit/fb55504913bff097819211eee53ab3c66184765b))


### Documentation

* update README source names ([f2041b7](https://github.com/chio-labs/sqlbuild/commit/f2041b78b544ecdd4e8a17139cf9d69b28be2551))

## [0.13.0](https://github.com/chio-labs/sqlbuild/compare/v0.12.0...v0.13.0) (2026-05-16)


### Features

* add Dagster asset loader ([6cf6e29](https://github.com/chio-labs/sqlbuild/commit/6cf6e29cb5c4887f2fa7e82bee60bd34768fc0e6))
* add Dagster CLI resource ([c718d55](https://github.com/chio-labs/sqlbuild/commit/c718d55a706e2e205722e548ec3ee5a9346d4019))
* add Dagster playground template ([718e77d](https://github.com/chio-labs/sqlbuild/commit/718e77d2cbc14d6760b7af5dac50d1249ef234db))
* add Dagster project preparation ([df92013](https://github.com/chio-labs/sqlbuild/commit/df9201367a8359fd838c12f142941d4e7a3c11b2))
* add Dagster scenario checks helper ([75473bd](https://github.com/chio-labs/sqlbuild/commit/75473bd36455132be1df12d25a737aa112c9e10a))
* add static DAG JSON output ([1c8f497](https://github.com/chio-labs/sqlbuild/commit/1c8f49752bd72719ab3b5ff4e9c02b28fbcc1d1b))
* bridge Dagster asset selections ([2e60398](https://github.com/chio-labs/sqlbuild/commit/2e603981c9ffc2aeab241645080fbbe41d68c3d3))
* emit Dagster events from execution JSON ([4e5e1b6](https://github.com/chio-labs/sqlbuild/commit/4e5e1b62898a32a9a3d060f5b6f3aca38587ad8b))
* select Dagster scenarios from assets ([6f584c8](https://github.com/chio-labs/sqlbuild/commit/6f584c83702689d90931006ba1bae19a5b2b1407))
* stream SQLBuild output in Dagster ([b603449](https://github.com/chio-labs/sqlbuild/commit/b60344921fb88fb780239dc55aaf0d160b30a5f7))
* tag SQLBuild Dagster asset kinds ([342bb61](https://github.com/chio-labs/sqlbuild/commit/342bb613dc022dd92f242a6035b1d2918ffd4926))


### Bug Fixes

* group Dagster assets by SQLBuild project ([00c324f](https://github.com/chio-labs/sqlbuild/commit/00c324fa7feced8ae78c4fca98e89a2bfff8eccc))
* improve Dagster demo and logging ([e120222](https://github.com/chio-labs/sqlbuild/commit/e12022213990de3c4fdf45708a0dfda8d8ddf157))

## [0.12.0](https://github.com/chio-labs/sqlbuild/compare/v0.11.0...v0.12.0) (2026-05-15)


### Features

* add sqlglot cte parsing fallback ([a45c3ea](https://github.com/chio-labs/sqlbuild/commit/a45c3ea3b68ee184a1a6ce26f93b72f2fb2d4eff))
* allow scenario fixtures to sample sources ([a348eb9](https://github.com/chio-labs/sqlbuild/commit/a348eb99f82456d6203274a7785f46670d4aef40))
* allow scenario fixtures to sample sources ([cc363ca](https://github.com/chio-labs/sqlbuild/commit/cc363cad2bacdfc75b8e115682b574a226242866))

## [0.11.0](https://github.com/chio-labs/sqlbuild/compare/v0.10.0...v0.11.0) (2026-05-15)


### Features

* add macro SQL test mode ([6498527](https://github.com/chio-labs/sqlbuild/commit/64985278ed1fb46d6af50d15e24f09eea8e2d544))
* add macro SQL test mode ([1e6c6c6](https://github.com/chio-labs/sqlbuild/commit/1e6c6c6904c1b304d5c39c11d1464c6103f5a075))
* add table function SQL tests ([3b07fc6](https://github.com/chio-labs/sqlbuild/commit/3b07fc6fb61e3aae995c3cf7b6821600b1ec5b4d))
* add table function SQL tests ([8e8c1e4](https://github.com/chio-labs/sqlbuild/commit/8e8c1e4cbe28be4703dd51cd5bb938fab6e55b8a))
* add UDF SQL test mode ([150b552](https://github.com/chio-labs/sqlbuild/commit/150b55225caab527a227f5568645b8e8a8437d2f))
* add UDF SQL test mode ([5738a42](https://github.com/chio-labs/sqlbuild/commit/5738a42c16d0041dffdb7c7ff5dedc16268d74e3))

## [0.10.0](https://github.com/chio-labs/sqlbuild/compare/v0.9.0...v0.10.0) (2026-05-14)


### Features

* add skills update command ([e2546eb](https://github.com/chio-labs/sqlbuild/commit/e2546eb6b6d8963ba60c80d858612a861f667487))

## [0.9.0](https://github.com/chio-labs/sqlbuild/compare/v0.8.0...v0.9.0) (2026-05-14)


### Features

* add dbt interop debug ([8d71604](https://github.com/chio-labs/sqlbuild/commit/8d7160440446e9a242c3a67b028f50e15a8b7134))
* add dbt interop foundation ([6d548b9](https://github.com/chio-labs/sqlbuild/commit/6d548b9c386895e707fcbb3a118f24bfc9cb6c26))
* add dbt interop plan output ([9e5d012](https://github.com/chio-labs/sqlbuild/commit/9e5d0123001a9530e307e97ba485d7a88d2763cc))
* add warehouse zero copy clone support ([fef64e8](https://github.com/chio-labs/sqlbuild/commit/fef64e8dc1b2cda62c0419d793a1a7ec8cdfa030))
* build dbt combined graph ([a6ca203](https://github.com/chio-labs/sqlbuild/commit/a6ca203fd9b6f4aa989d3d059c0364048884fbc3))
* execute dbt interop run and build ([91e80a5](https://github.com/chio-labs/sqlbuild/commit/91e80a5e10cc9e9c91533c61ae0c86e919c79b23))
* execute dbt interop tests ([cd3c556](https://github.com/chio-labs/sqlbuild/commit/cd3c55678db2df8d2500300ad3624575558f1e2b))
* mock dbt refs in tests and scenarios ([0bc7d40](https://github.com/chio-labs/sqlbuild/commit/0bc7d40e8e6649390b4dd7df969dfb0343ac3ce5))
* orchestrate dbt interop plans ([92e8f39](https://github.com/chio-labs/sqlbuild/commit/92e8f39ae03f81e1b09c08c3aa463a6f61c7d042))
* refine dbt plan output ([4090fa6](https://github.com/chio-labs/sqlbuild/commit/4090fa6a927e7fcf5dada88aa7e124c3d4ed11cd))
* refine plan section layout ([0ea662c](https://github.com/chio-labs/sqlbuild/commit/0ea662c410065efa8363949014668f19e31541c0))
* resolve dbt interop selections ([87cdd3a](https://github.com/chio-labs/sqlbuild/commit/87cdd3a6c3b5f90ca3fdfa0b791be2dd1374234f))
* resolve dbt refs from manifest ([0ab4921](https://github.com/chio-labs/sqlbuild/commit/0ab49216ea0b43c2f293556132aa5074c9bd6ad7))
* route dbt interop arguments ([7fc4da3](https://github.com/chio-labs/sqlbuild/commit/7fc4da3aa2f615584c169a0781cf690ac31b1881))
* support adapter sqlglot dialect setting ([56926f3](https://github.com/chio-labs/sqlbuild/commit/56926f34bf8ad197f7c556355d87eead4a01f7fc))
* wire dbt interop plan cli ([80d72d8](https://github.com/chio-labs/sqlbuild/commit/80d72d8e4fbb0b2ec85486b71840b27a050a02bf))


### Bug Fixes

* default audit severity to error ([98f0dea](https://github.com/chio-labs/sqlbuild/commit/98f0dea12cdbc09c7ef5dbe58b79082985d5931d))
* default audit severity to error ([f9cf03f](https://github.com/chio-labs/sqlbuild/commit/f9cf03f88e00a581c74d3438c5e041bc621724ee))
* escape reference example calls ([bf8273f](https://github.com/chio-labs/sqlbuild/commit/bf8273fb9a9aec2997384d213ca6f4be37470fee))
* keep local replay error fixtures valid ([7f48d4c](https://github.com/chio-labs/sqlbuild/commit/7f48d4c48fdae80979bef3a2b2db943b06b74af5))
* recognize dbt scenario artifacts ([c1f3274](https://github.com/chio-labs/sqlbuild/commit/c1f3274db1ef82aa78f597c97bd25063ea00f6b3))
* recognize dbt scenario artifacts ([6b8a5f5](https://github.com/chio-labs/sqlbuild/commit/6b8a5f542fbe19d4a824ba3a5b310f9ad840b808))
* reject dbt refs in audits ([e384ed1](https://github.com/chio-labs/sqlbuild/commit/e384ed185e31c2e0dbbccb826bed0b40f222240c))
* remove dbt mock fixture model ([e1c3a8d](https://github.com/chio-labs/sqlbuild/commit/e1c3a8da182bb0dce71c9917ad4d29fe19e1cc6a))
* render coded dbt interop errors ([12395a1](https://github.com/chio-labs/sqlbuild/commit/12395a19e7fbbb82971b814858cace906642f192))
* require sqlglot for scenario snapshots ([7b6cf94](https://github.com/chio-labs/sqlbuild/commit/7b6cf94d4fbfad66581b0279909830aaabcf5f9a))
* resolve dbt interop paths absolutely ([c3a21ee](https://github.com/chio-labs/sqlbuild/commit/c3a21ee5e42ac9e9fe8fab79e6c0c08066a8862b))
* stop ambient dbt manifest discovery ([9e35257](https://github.com/chio-labs/sqlbuild/commit/9e35257b0e12f2c68d8525d684d2f96ac179582b))


### Documentation

* use absolute readme logo url ([a5b5d2c](https://github.com/chio-labs/sqlbuild/commit/a5b5d2c8003aa41125752a084b36865e6d7e62bc))

## [0.8.0](https://github.com/chio-labs/sqlbuild/compare/v0.7.0...v0.8.0) (2026-05-09)


### Features

* add scenario test CLI ([8ff989a](https://github.com/chio-labs/sqlbuild/commit/8ff989a4bc98fbf095b39106bf6b73f88aec071e))
* add SQL unit test assertions ([640fbcb](https://github.com/chio-labs/sqlbuild/commit/640fbcb2fdcb090bba221524af32d665427a557e))
* add waffle shop playground ([a91f805](https://github.com/chio-labs/sqlbuild/commit/a91f805ac8a0eeaf5bf830a2dfdfe0d22c85f2e0))
* clean scenario artifacts ([2293a8a](https://github.com/chio-labs/sqlbuild/commit/2293a8a97098c3fa5a90ae7314dc06f1a89875bd))
* clean scenario artifacts with janitor ([19df620](https://github.com/chio-labs/sqlbuild/commit/19df620850dee53bf09724f91a3f3469d2468e13))
* discover SQL scenarios ([d280dff](https://github.com/chio-labs/sqlbuild/commit/d280dff043714a7f48dc1b5de0c63291b06bdd68))
* execute scenario checks ([a32ad16](https://github.com/chio-labs/sqlbuild/commit/a32ad16e2607fa02c6678c4582167c8ce0118cc0))
* execute scenario model graph ([8cba144](https://github.com/chio-labs/sqlbuild/commit/8cba1444d1fa3fd0dadcdae989a69fc810206960))
* extract scenario CTE roles ([0ecbabf](https://github.com/chio-labs/sqlbuild/commit/0ecbabfba117c7eca1d3e4635e5117ac508f47b5))
* infer scenario graph requirements ([555d545](https://github.com/chio-labs/sqlbuild/commit/555d54514cb6e0e4f664040c573901dcc0ed15b6))
* load scenario project seeds ([0b52756](https://github.com/chio-labs/sqlbuild/commit/0b52756863816e7aa1d15af273619b607ea73293))
* materialize scenario fixtures ([b49179a](https://github.com/chio-labs/sqlbuild/commit/b49179a2990aeb9b6cb7fe2c48bdd2c83b7a3784))
* name scenario artifacts ([93e0cb6](https://github.com/chio-labs/sqlbuild/commit/93e0cb6de5eddafbc6b7969fce90069ddba1d63f))
* plan scenario fixture SQL ([8fd0a69](https://github.com/chio-labs/sqlbuild/commit/8fd0a69e732d03620d4fa6cc2b50e83b77a8ceb0))
* plan scenario relation overrides ([1dfb94b](https://github.com/chio-labs/sqlbuild/commit/1dfb94bc8797cf0250f517eedc91015e7040306b))
* show nested SQL unit test checks ([b096564](https://github.com/chio-labs/sqlbuild/commit/b0965646820fc96e27e4576b37e9e25bf00f7eb8))
* write scenario runtime artifacts ([8add531](https://github.com/chio-labs/sqlbuild/commit/8add531783f03dc348368f6547e61da941f0ec16))


### Bug Fixes

* keep playground install minimal ([e67a144](https://github.com/chio-labs/sqlbuild/commit/e67a14464c90653373eddd4bdfef46855802a6fc))

## [0.7.0](https://github.com/chio-labs/sqlbuild/compare/v0.6.0...v0.7.0) (2026-05-07)


### Features

* add accepted values and relationships audits ([7a12fd3](https://github.com/chio-labs/sqlbuild/commit/7a12fd3098dfe885a73f7a8922daa28e3893a1e0))
* add nullable contracts and built-in audits ([611f99a](https://github.com/chio-labs/sqlbuild/commit/611f99a689440b29af5ebe835e27de6967c60d8d))
* add spinner based CLI progress ([9cce465](https://github.com/chio-labs/sqlbuild/commit/9cce465c454895bc79a35e9bee3cadbcd2ca34b3))
* add spinner based CLI progress ([9664cd9](https://github.com/chio-labs/sqlbuild/commit/9664cd9eb608819806cc2d7f9d59d57ecedbf987))
* align config and table function names ([b011ead](https://github.com/chio-labs/sqlbuild/commit/b011eadb0b9d3991dcdf53f522bb8d6f73682974))
* align config and table function names ([ec77895](https://github.com/chio-labs/sqlbuild/commit/ec7789511c095bd1d572a570e73a5a8e5867598d))
* show progress errors below rows ([cbe4a2a](https://github.com/chio-labs/sqlbuild/commit/cbe4a2a76232c0b854a369e5af02f5ebb0fbc5d8))
* show progress errors below rows ([4908b24](https://github.com/chio-labs/sqlbuild/commit/4908b24ef7e9d627d5c354dc5ebebdc255a38991))
* unify authored SQL interpolation ([c1d7e77](https://github.com/chio-labs/sqlbuild/commit/c1d7e77ec2545877949d59288d7c942afe031de3))
* unify CLI progress output ([0695eea](https://github.com/chio-labs/sqlbuild/commit/0695eeaca6b49e15152bead00e578c1f647c4936))


### Bug Fixes

* align plan output columns ([8af7b74](https://github.com/chio-labs/sqlbuild/commit/8af7b740be77138b773fb44a4366a14bbad5d828))
* narrow function change fingerprints ([5bc5896](https://github.com/chio-labs/sqlbuild/commit/5bc58967bfa26e6330a78d4657f19a2bb4fd13ee))
* narrow function change fingerprints ([a0bf9bf](https://github.com/chio-labs/sqlbuild/commit/a0bf9bf4a020a84066078d798b9b9fc76af7b591))
* respect disabled sqlglot setting ([11ca558](https://github.com/chio-labs/sqlbuild/commit/11ca55858ac91a9be060f22b100fca4a938c80ac))


### Documentation

* add contributing guide and update logo ([4e3ce74](https://github.com/chio-labs/sqlbuild/commit/4e3ce748497d3eec80b85387f9f9e261ee715c30))
* use relative README logo path ([0203ad8](https://github.com/chio-labs/sqlbuild/commit/0203ad8ca827f8d9c23309432601ce27b27b4b82))

## [0.6.0](https://github.com/chio-labs/sqlbuild/compare/v0.5.0...v0.6.0) (2026-05-07)


### Features

* add column lineage analyzer ([f60c65d](https://github.com/chio-labs/sqlbuild/commit/f60c65d1b4fd7d7d9512d75023f829888e555fb6))
* add column lineage CLI traces ([83977a0](https://github.com/chio-labs/sqlbuild/commit/83977a048fe6dc978909b85ddbf1c619ba39468f))
* add compile contract diagnostics ([0ba4d65](https://github.com/chio-labs/sqlbuild/commit/0ba4d65e66a1df8b519ac62a6b9e2941f0998b83))
* add conservative nullability inference ([74b6bb2](https://github.com/chio-labs/sqlbuild/commit/74b6bb22a614fae5c106a48032e54107b0b8a479))
* add fast compile lineage mode ([19fb926](https://github.com/chio-labs/sqlbuild/commit/19fb9261d13bb1947b990fe35a5363957cca2bc7))
* add lineage mode metadata ([726ebb0](https://github.com/chio-labs/sqlbuild/commit/726ebb04fa08178dbf323ad1632e03c341272af4))
* improve compile output ([8bb26f9](https://github.com/chio-labs/sqlbuild/commit/8bb26f97e5770895ea472dea27f06cda3d50ff9c))
* make compile offline ([0099e0d](https://github.com/chio-labs/sqlbuild/commit/0099e0d61f458f68ba14b53531826a5ac77c9fa6))
* scope rich column lineage ([521e47a](https://github.com/chio-labs/sqlbuild/commit/521e47adfde3f6cdb42cc8b5772553df4ca20e91))

## [0.5.0](https://github.com/chio-labs/sqlbuild/compare/v0.4.0...v0.5.0) (2026-05-06)


### Features

* switch project config to TOML ([e7127b0](https://github.com/chio-labs/sqlbuild/commit/e7127b00663b4773d1897500ebc1492b25dff285))
* switch project config to TOML ([b6f208d](https://github.com/chio-labs/sqlbuild/commit/b6f208d7ca8f39a7bf9bce15c9d964a2df90f941))

## [0.4.0](https://github.com/chio-labs/sqlbuild/compare/v0.3.0...v0.4.0) (2026-05-05)


### Features

* add debug command ([b7a67f5](https://github.com/chio-labs/sqlbuild/commit/b7a67f5fbc4bcb963ac36988f6a18a9127742d91))
* add debug command ([1193f75](https://github.com/chio-labs/sqlbuild/commit/1193f75149787bac84f3907ef166409020a64814))

## [0.3.0](https://github.com/chio-labs/sqlbuild/compare/v0.2.1...v0.3.0) (2026-05-05)


### Features

* add lineage command ([9aef7d6](https://github.com/chio-labs/sqlbuild/commit/9aef7d69ad556a2ef0ec568f1aed4492a119dfff))
* add lineage command ([a0af73a](https://github.com/chio-labs/sqlbuild/commit/a0af73adfd5dba1870ff5b3b7293a78967a578c8))

## [0.2.1](https://github.com/chio-labs/sqlbuild/compare/v0.2.0...v0.2.1) (2026-05-05)


### Bug Fixes

* render README correctly on PyPI ([8abf270](https://github.com/chio-labs/sqlbuild/commit/8abf270a77aabd1040ce223fc9f377eb168bfe39))
* render README correctly on PyPI ([8251c0d](https://github.com/chio-labs/sqlbuild/commit/8251c0d6bf5b8277d36a7756c1fa95b04d1df698))

## [0.2.0](https://github.com/chio-labs/sqlbuild/compare/v0.1.0...v0.2.0) (2026-05-05)


### Features

* add --defer-to support with deferred target resolution, buildability checks, and SC026 limit fix ([2097d80](https://github.com/chio-labs/sqlbuild/commit/2097d8020b3c0aa970ab7b7b038ab2aa2534fe09))
* add --json output flag for sqb compile and sqb plan commands ([008d938](https://github.com/chio-labs/sqlbuild/commit/008d938ca6dfc53a4dbeab9aa63c5b9024a97596))
* add --verbose flag to build/run showing full model DDL and audit SQL inline ([3f3cfe0](https://github.com/chio-labs/sqlbuild/commit/3f3cfe01dd256effdf71d24200b425cd10660337))
* add adapter spine with base/strict adapters and compile assembly ([b72fbff](https://github.com/chio-labs/sqlbuild/commit/b72fbff3b15680b795ddaa864c867b451cfb9f7f))
* add append cursor boundary control ([796af13](https://github.com/chio-labs/sqlbuild/commit/796af130cfa2fa79e595023187a950043bc34336))
* add audit scheduling with attachment resolution, graph validation, and effective run scope degradation ([587d51e](https://github.com/chio-labs/sqlbuild/commit/587d51ebd44a28b8d64c5cb1413443710a52e4ec))
* add audit/test plan entries with chained test resolution and unresolved ref validation ([b1e0be7](https://github.com/chio-labs/sqlbuild/commit/b1e0be74183a454e34662c1ca675e44fcce1c3fb))
* add backfill cascade propagation with duration comparison, root cause attribution, and cross-type rules ([f27eb09](https://github.com/chio-labs/sqlbuild/commit/f27eb09435bff1a53b9eb27393271e7cb815193e))
* add BigQuery adapter support ([f79ff90](https://github.com/chio-labs/sqlbuild/commit/f79ff90b813cf751d5a5313416eb9a0be3ff60e7))
* add BigQuery warehouse parity ([1415f8e](https://github.com/chio-labs/sqlbuild/commit/1415f8e7ba8e48457d5ed0691a486212a85dee3a))
* add build executor with topo execution, failure propagation, source/end audits, and direct/staged mode support ([d31466d](https://github.com/chio-labs/sqlbuild/commit/d31466d51d55234f4a73c66dd6b59e9a49f853b2))
* add build output formatter with live progress, color support, and duration tracking ([42d1218](https://github.com/chio-labs/sqlbuild/commit/42d12183b2c3dd012f541d5cc8d753ae634bf09e))
* add buildability checks validating upstream deps exist in scope or warehouse ([00f8c99](https://github.com/chio-labs/sqlbuild/commit/00f8c9946be85cb3e79416caa86e854fb3ea2230))
* add change detection with query/schema comparison, backfill policy resolution, and SC033 cross-package import rule ([97e4582](https://github.com/chio-labs/sqlbuild/commit/97e45826398882c381f936ebf15cbf271a11c885))
* add clone command support ([350a94b](https://github.com/chio-labs/sqlbuild/commit/350a94bd2698ee6ced0bd5b3604c0597b6de6c1f))
* add compile input attachment layer ([724c936](https://github.com/chio-labs/sqlbuild/commit/724c9364d565623537a974effff6723966c4adcf))
* add compile-time sql macro expansion ([1e78559](https://github.com/chio-labs/sqlbuild/commit/1e78559591edf9c081c358760a0474206e4494a4))
* add compile-time SQL syntax validation with project, model, and CLI escape hatches ([02b16f5](https://github.com/chio-labs/sqlbuild/commit/02b16f55655936d5d706a9fbcf0878915be8c02b))
* add concurrent build scheduler with ready-queue DAG dispatch ([92ad4c4](https://github.com/chio-labs/sqlbuild/commit/92ad4c48342ee94df59e288838e5f4a20c7e2d87))
* add ctx.execute_sql() for custom materializations and require statement_recorder on adapter write methods ([353b1ea](https://github.com/chio-labs/sqlbuild/commit/353b1eaf995ee7c47c2fa1c27b8d59be2c479ca9))
* add cursor start floors ([a47cfa5](https://github.com/chio-labs/sqlbuild/commit/a47cfa5be7cf7a85718dbc46fe79c599ec56fb54))
* add cursor_type/validation/typed overrides/sql vars with StrEnum enforcement ([418925c](https://github.com/chio-labs/sqlbuild/commit/418925c3b5d9eefe33ed3303b09e647c6354810a))
* add custom materializations with @[@placeholder](https://github.com/placeholder) support and user-callable audits ([d9e1592](https://github.com/chio-labs/sqlbuild/commit/d9e1592560f6fbb31d210046f3f9c84e5fbb43e7))
* add Databricks adapter support ([e692ce6](https://github.com/chio-labs/sqlbuild/commit/e692ce64e19a7156d5c1a6ff7a41b9401107e2e7))
* add Databricks Python UDF support ([849e759](https://github.com/chio-labs/sqlbuild/commit/849e759b5aa95c26c65e733d704e3f7057f7cf3a))
* add DuckDB adapter with full method coverage and remove unused ResolutionMixin ([57ec8d9](https://github.com/chio-labs/sqlbuild/commit/57ec8d97ad5a12d254c492c8ceccadde2797eb18))
* add e2e tests for all CLI commands and fix --project-dir relative database path resolution ([170b4b5](https://github.com/chio-labs/sqlbuild/commit/170b4b564c2e61462f12917b6a7b82fb37d4fbca))
* add environment diff command support ([c46fdca](https://github.com/chio-labs/sqlbuild/commit/c46fdca731bcfef3d30242c14337e7c76afd47b9))
* add executor build runtime stage 1 spec and validation enums, settings, audit severity/run_scope resolution, and non-incremental config guards ([70172f1](https://github.com/chio-labs/sqlbuild/commit/70172f160f3da29b9b7aa1ef882743e70f006d0f))
* add fingerprint storage with per-schema read/write and hash computation ([727b2d5](https://github.com/chio-labs/sqlbuild/commit/727b2d5857fa804035f5b9ff5ae815b911807278))
* add incremental executor with delta/DML lifecycle, schema change handling, and adapter DDL methods ([cf20aec](https://github.com/chio-labs/sqlbuild/commit/cf20aec008dd817599c313f6163a939dad10f203))
* add Layer 5 ref resolution with cursor bounds, source CAST wrapping, and batched snapshot gathering ([4bf9975](https://github.com/chio-labs/sqlbuild/commit/4bf9975a22c95845b4d864770f4f962802df9daf))
* add Layer 6 materialization strategy, plan output, and execution plan orchestration ([4061622](https://github.com/chio-labs/sqlbuild/commit/4061622247faced889fd5504264a54013f2c3672))
* add manifest writer module with dbt v12-compatible serialization ([32f20f2](https://github.com/chio-labs/sqlbuild/commit/32f20f2581edf2c72f8e99bfc7f33c5159059814))
* add max concurrency project setting ([43b3ab5](https://github.com/chio-labs/sqlbuild/commit/43b3ab5d598876d59774217a5b8eea53845cae24))
* add microbatch executor with sentinel substitution, cursor-range delete_insert, and batch splitting ([d1eb879](https://github.com/chio-labs/sqlbuild/commit/d1eb87987412ddb5ef3c42539514b2dcd6d2321c))
* add model target context to compile templates ([45db2e9](https://github.com/chio-labs/sqlbuild/commit/45db2e99ab8f41ab23c3d395d87259e9d55caedd))
* add on_progress callback to custom materialization context ([e717ff5](https://github.com/chio-labs/sqlbuild/commit/e717ff5a6b7b45808953ee12b7112866ff467fba))
* add optional sqlglot test projection parsing ([b75f9d7](https://github.com/chio-labs/sqlbuild/commit/b75f9d7581686b351fcc941c9e23f780ba0aaaa3))
* add path:folder selector resolution and --no-sql-validation CLI flag ([d6b3951](https://github.com/chio-labs/sqlbuild/commit/d6b39515e734d9cf699b3ee2071c881745b42959))
* add plan display before build execution and use_color support on plan formatter ([752bbad](https://github.com/chio-labs/sqlbuild/commit/752bbad4f6ee7a525f7cd41d540ea7846a85bba7))
* add planner graph helpers with topo sort, expansion, and path finding ([3fcab8e](https://github.com/chio-labs/sqlbuild/commit/3fcab8eb25de793c96dfc26d13a42246a6b62493))
* add planner-ready compiled resource models and dependency helpers ([fee76a9](https://github.com/chio-labs/sqlbuild/commit/fee76a97888988a0ec9e6c5ec11f1f098c003459))
* add project-local adapter discovery ([ea7d06d](https://github.com/chio-labs/sqlbuild/commit/ea7d06d45a4dc446ce8190f2f3a6cc6a4ffc2b58))
* add Python UDF support ([e9c8e22](https://github.com/chio-labs/sqlbuild/commit/e9c8e224b152653071a1f653501f1b9ba654cbe2))
* add query command ([c80a508](https://github.com/chio-labs/sqlbuild/commit/c80a508fcaec051a7aaff9a54f0002a090bba239))
* add query command ([ffe1435](https://github.com/chio-labs/sqlbuild/commit/ffe143545ffb0d8dab2ff77ef496601dc99d7ff3))
* add raw schema metadata discovery ([22811f8](https://github.com/chio-labs/sqlbuild/commit/22811f8eba52a603901025e82d11bfcca5e437e1))
* add raw source discovery parsing ([0ff1185](https://github.com/chio-labs/sqlbuild/commit/0ff11850d0d0184c8906f096f668b46eb15792b8))
* add raw sql audit discovery parsing ([e62b123](https://github.com/chio-labs/sqlbuild/commit/e62b1233d2f1cc66c513c3a07395cd4d72b1420a))
* add rich diff summary output ([9743b7b](https://github.com/chio-labs/sqlbuild/commit/9743b7b4fe06579d9a649979ef8a0b22b58a8fda))
* add runtime audit rendering with relation overrides, AuditOutcome enum, and AuditExecutionResult model ([8272844](https://github.com/chio-labs/sqlbuild/commit/82728445a5582a8d3270b6927d081a316027cc4b))
* add runtime SQL statement recorder ([f3e943e](https://github.com/chio-labs/sqlbuild/commit/f3e943ed33ca9697a042970b001d3fa7a224cbae))
* add safe janitor cleanup command ([ec1e02c](https://github.com/chio-labs/sqlbuild/commit/ec1e02ccfb89681a7ffa9b0820b50b8c2d125409))
* add seed target overrides ([4c89d0c](https://github.com/chio-labs/sqlbuild/commit/4c89d0ca21dcc0031a9047a5402090f4fea40689))
* add selector parsing and scope resolution with union, intersection, and exclude ([fe8a17b](https://github.com/chio-labs/sqlbuild/commit/fe8a17b6e13627335ecbe5e3b6d0a43f8aac4b76))
* add shared type normalization ([3a3103a](https://github.com/chio-labs/sqlbuild/commit/3a3103a22072686f10bf688b24328191dcbd6c18))
* add shared type normalization ([ac7d895](https://github.com/chio-labs/sqlbuild/commit/ac7d89533bdd0a0e873ebce77496fa626553c5fd))
* add snowflake adapter support ([0da4ecf](https://github.com/chio-labs/sqlbuild/commit/0da4ecf94528212b59262d640b40cfe23f5aac9a))
* add source quality metadata parsing ([6ec1e1e](https://github.com/chio-labs/sqlbuild/commit/6ec1e1e76834998e47fe83c094d580b5a59c1dd8))
* add sqb compile command with pipeline orchestration, target writer, and adapter defaults ([2446785](https://github.com/chio-labs/sqlbuild/commit/2446785ad6861c2286d027db6125f9aedc2def09))
* add sqb plan command with compact/verbose output, waffle_shop example, and seed ref fixes ([038314b](https://github.com/chio-labs/sqlbuild/commit/038314b788a5da3d15616cfc9d57a75d0ebfaf47))
* add SQL table functions ([52aaadd](https://github.com/chio-labs/sqlbuild/commit/52aaaddbc11b7017a0790f4742f70af789a41667))
* add SQL table functions ([d6e9a04](https://github.com/chio-labs/sqlbuild/commit/d6e9a0468bc8195e2117a1d8409614910b6d667f))
* add SQL UDF resources ([24149b0](https://github.com/chio-labs/sqlbuild/commit/24149b001c7cbe565fda2b66f521932a68f04158))
* add sql-style model headers ([7a80177](https://github.com/chio-labs/sqlbuild/commit/7a801779042dbd5ed18e2729ed695b4b123760de))
* add sqlbuild as an alias for sqb CLI entry point ([d69535e](https://github.com/chio-labs/sqlbuild/commit/d69535ed71738dc9150e60d8e3df089e43d6bf81))
* add sqlglot column inference for schema change detection with source attribution ([c68ef74](https://github.com/chio-labs/sqlbuild/commit/c68ef743c843ac144bd4494012d36043a530229d))
* add table executor with staged/direct lifecycle, type enforcement, audit execution, hooks, and fingerprint write ([36de9f2](https://github.com/chio-labs/sqlbuild/commit/36de9f27361b75138e7f294a65d9abc3de6bc1ca))
* add template expression helpers ([23b3a2b](https://github.com/chio-labs/sqlbuild/commit/23b3a2be6b4ffa18f1d71c18494f9c8042b33496))
* add transaction() context manager and transactional atomicity tests ([497b613](https://github.com/chio-labs/sqlbuild/commit/497b613d5349038b1079da919095cbc895c59af2))
* add type_enforcement flag to schema change detection for yml vs inferred precedence ([c97e8d3](https://github.com/chio-labs/sqlbuild/commit/c97e8d36638024694c15d5d57cebb17e8c7bc45e))
* add view executor, SQL unit test executor, and planner test ordering for Stage 8 ([38890d8](https://github.com/chio-labs/sqlbuild/commit/38890d89fce9b06baeff2087e09ec33815d353b3))
* add warehouse cursor type consistency check with heuristic and sqlglot classification ([0726216](https://github.com/chio-labs/sqlbuild/commit/0726216864c2707c61ced52ad077afaacb35896c))
* add warehouse snapshot gathering with bulk relation, column, and fingerprint reads ([c09e764](https://github.com/chio-labs/sqlbuild/commit/c09e764ae609e6ae7fe9963b02251d7583c16044))
* attach defaults and path defaults to compile model inputs ([8aec92c](https://github.com/chio-labs/sqlbuild/commit/8aec92c7fcbc0cd61e747efea1ce4abb366c0461))
* bootstrap repo and port convention checkers ([4967f63](https://github.com/chio-labs/sqlbuild/commit/4967f63fde8d68b1947f03988b63346ef9a73280))
* compile attached generic audits ([b619e53](https://github.com/chio-labs/sqlbuild/commit/b619e539e061f7d4df5b7a6b5af1dc0176b8f1c2))
* compile test and audit sql surfaces ([9482476](https://github.com/chio-labs/sqlbuild/commit/9482476fd72e54daf06e9fd027ce76e6b4c50272))
* default audits to delta and final ([25099c2](https://github.com/chio-labs/sqlbuild/commit/25099c2669679b683ad5fb1b0cba605504343a79))
* enforce typed source columns by default ([6d80f38](https://github.com/chio-labs/sqlbuild/commit/6d80f3898148b7667e6c388e0194e8fe440aae9e))
* enforce typed source columns by default ([4fd4e9b](https://github.com/chio-labs/sqlbuild/commit/4fd4e9b2d2fe03dc0017b435d9e1bc220ec85be6))
* expand compile templates in config layers ([f21b124](https://github.com/chio-labs/sqlbuild/commit/f21b124a2f1f7c822b4607fc41556180c47af97c))
* expand diff examples and samples ([884693f](https://github.com/chio-labs/sqlbuild/commit/884693f0c35da2ded25542dd797940870a516b71))
* expand discovery parsing and cli error handling ([69f23e2](https://github.com/chio-labs/sqlbuild/commit/69f23e2d34a029fa536e1b21047b8027ea756442))
* expand path selector endpoint syntax ([938ec22](https://github.com/chio-labs/sqlbuild/commit/938ec22979fdb9899b89450ddfc1e00bbb67db49))
* expand SQL UDF compile inputs ([9d6f2df](https://github.com/chio-labs/sqlbuild/commit/9d6f2df51a58c2f3b2209608af1c567548ed9242))
* extract logical sql references during compile ([01517e6](https://github.com/chio-labs/sqlbuild/commit/01517e6e8fee2c43cc735d5889b0b3c5990260d5))
* extract sql test cte semantics during compile ([65b789a](https://github.com/chio-labs/sqlbuild/commit/65b789a3290f842e616f40502c0e62d5eb9c6712))
* filter warehouse metadata by selected scope ([e10cd8a](https://github.com/chio-labs/sqlbuild/commit/e10cd8a3c26aab5c40bc8a32c522e7884a54663d))
* finish lifecycle event logging ([d907eb5](https://github.com/chio-labs/sqlbuild/commit/d907eb551b26b55df768716a9488246552bd97a7))
* guard unit test sql length ([7af7856](https://github.com/chio-labs/sqlbuild/commit/7af7856d0bd02cafc3f1d0cd4278abb6664fcdbc))
* improve chained sql test output ([2732950](https://github.com/chio-labs/sqlbuild/commit/273295085e52d4775bd879e53f5774edf1186625))
* make seed resources explicit ([f635894](https://github.com/chio-labs/sqlbuild/commit/f635894b5ea598b6271c8aaa9dcbabde50033e69))
* move model metadata into headers ([18d5481](https://github.com/chio-labs/sqlbuild/commit/18d54813b09d22c04112a19934041fc6920e619e))
* move model metadata into headers ([dd7f980](https://github.com/chio-labs/sqlbuild/commit/dd7f9808e37feef27585341fb8862ea4aff478dc))
* move statement recording into adapter write methods ([e2c6625](https://github.com/chio-labs/sqlbuild/commit/e2c66250bcc7c1f9665ab79d8eafddce0741e194))
* redesign plan formatter with grouped output, cascade display, microbatch labels, and enum-only domain strings ([08004cc](https://github.com/chio-labs/sqlbuild/commit/08004cc13f8986d9763724586c1b170acf203920))
* refine debug diagnostics output ([306506b](https://github.com/chio-labs/sqlbuild/commit/306506bcfac4635ed8de5d0bafc944395812217c))
* resolve compile environment and vars layering ([67931de](https://github.com/chio-labs/sqlbuild/commit/67931de95e403a175af5f64aedc203f97d6772b0))
* show delta/final audit phases with batch counts and aggregate microbatch audit results ([30bfde1](https://github.com/chio-labs/sqlbuild/commit/30bfde146d30bad70e3b976312d4f485d6e7f33c))
* show executed lifecycle SQL in verbose output ([509cc03](https://github.com/chio-labs/sqlbuild/commit/509cc039bc63d797b46efbcd67a78cd2147e2e7d))
* split early run context from target templates ([9b30f31](https://github.com/chio-labs/sqlbuild/commit/9b30f31572b489e1b08e72aa7e0fa9cae0229fe6))
* support double quoted model header strings ([5212d40](https://github.com/chio-labs/sqlbuild/commit/5212d40b299f26c5834d5dfb4d980fb0e1d714e6))
* support expression-backed sources ([2d8a693](https://github.com/chio-labs/sqlbuild/commit/2d8a69355a18ea48905568704e2af417fcf7f860))
* support local connection settings ([fa900cd](https://github.com/chio-labs/sqlbuild/commit/fa900cdcb08d24d8cf8ba3d34dba494596983c7a))
* support local environment overrides ([fd84b1e](https://github.com/chio-labs/sqlbuild/commit/fd84b1eced7b8f0e8a2dd8fe27b9bad4187a477c))
* support local environment overrides ([deeb521](https://github.com/chio-labs/sqlbuild/commit/deeb521993167a472480dd8a8080e178d4835d67))
* support seed mocks in SQL tests ([ddeea1c](https://github.com/chio-labs/sqlbuild/commit/ddeea1cc327375858604475146e6d1809ea794aa))
* support sql test macro mocks ([d4b7c84](https://github.com/chio-labs/sqlbuild/commit/d4b7c84c0990db71e2ec35b29f0beead1aa70e66))
* UNFINISHED (trying to introduce lifecycle events) ([aafbdba](https://github.com/chio-labs/sqlbuild/commit/aafbdba89b0130cafb3af4f8719c782fda1c08e1))
* use environment range for diff ([7abe590](https://github.com/chio-labs/sqlbuild/commit/7abe5901418580d732b461ac3dc63ea06718c917))
* use environment range for diff ([12b76ef](https://github.com/chio-labs/sqlbuild/commit/12b76ef00f3ff2a33eb4544a072f98410928368a))
* validate discovery conflicts and seed metadata ([9dd6622](https://github.com/chio-labs/sqlbuild/commit/9dd6622abe1ffb79ce7f226066e5b2e0438e3fbf))
* validate seed csv headers in discovery ([e2357a5](https://github.com/chio-labs/sqlbuild/commit/e2357a51d3fd2c80a6e33061445648ffadd808e8))
* wire CLI commands for build, run, test, audit, and seed ([4d82460](https://github.com/chio-labs/sqlbuild/commit/4d82460bfe9a8522c57321f674bda4145b539688))
* wire custom materialization loading through compile pipeline and add waffle shop example with e2e coverage ([dad1f75](https://github.com/chio-labs/sqlbuild/commit/dad1f75d79883e397431c3e786f8de89a8abc25d))
* write runtime SQL artifacts after build and run ([293a29c](https://github.com/chio-labs/sqlbuild/commit/293a29ce3b3d351d7cee60d84416487d6f24da78))


### Bug Fixes

* align query fingerprint tracking ([a3307bc](https://github.com/chio-labs/sqlbuild/commit/a3307bc30885c0e1a43600b140b9d76ba502bb22))
* clarify audit failure messaging ([4c2a090](https://github.com/chio-labs/sqlbuild/commit/4c2a0909540111b9c67827f611b189f7419937e3))
* clarify CLI errors and DuckDB UDF fingerprints ([82921f9](https://github.com/chio-labs/sqlbuild/commit/82921f9423f975b0fd34d20601ee1a2648052d35))
* clarify CLI errors and DuckDB UDF fingerprints ([4d5801e](https://github.com/chio-labs/sqlbuild/commit/4d5801eeb1c99dc97044268dafef78b43959512a))
* coarsen mixed timestamp cursor replay ([a53901e](https://github.com/chio-labs/sqlbuild/commit/a53901eed994d2dc030c67e11b6c1848fe78b0e9))
* consolidate duplicate _get_materialization_type and add advanced custom materialization tests ([b9d3f9d](https://github.com/chio-labs/sqlbuild/commit/b9d3f9d987122484f26782060e167d0f999a1454))
* correct SKIP semantics, enforce incremental strategy, fix deferred cursor resolution ([bc7c344](https://github.com/chio-labs/sqlbuild/commit/bc7c3448b94618082ab0625bd4bd0eccd6a5de19))
* enforce cascade backfill planning ([fa18cbb](https://github.com/chio-labs/sqlbuild/commit/fa18cbbc9e03ac7ed33502d94dbb32f7e5050653))
* enforce cascade backfill planning ([214e294](https://github.com/chio-labs/sqlbuild/commit/214e29441ab972ab146475b8112de789f4eb7a29))
* handle runtime-owned cursor filters on first build ([e7b9202](https://github.com/chio-labs/sqlbuild/commit/e7b9202175cc0145735a9306237b8c041cfb4ad6))
* harden microbatch full-refresh execution ([43aa3fc](https://github.com/chio-labs/sqlbuild/commit/43aa3fca70b26fc6878f03040a5ccad52d7e4ef9))
* improve CLI output formatting and add Execution section header ([f3a67f3](https://github.com/chio-labs/sqlbuild/commit/f3a67f33864cddb4673a02b35cde9ee4a645cb49))
* improve plan/execution CLI output visual hierarchy and spacing ([eb1b0ed](https://github.com/chio-labs/sqlbuild/commit/eb1b0edcff08543328b22a7a135460870900d87f))
* improve standalone audit and test output with model grouping and consistent header styling ([c0475ae](https://github.com/chio-labs/sqlbuild/commit/c0475aec81f58e29592e5254e7c28f179512dc16))
* improve warehouse planning feedback ([70fc2a4](https://github.com/chio-labs/sqlbuild/commit/70fc2a46a0f3d2ebdd62611a87741142a1ef43a5))
* improve warehouse planning feedback ([17dd900](https://github.com/chio-labs/sqlbuild/commit/17dd90029a297d4d5df5e7518e7f22ffeb9897fb))
* indent audit and test sub-lines for clearer visual nesting under parent model ([bf2a2c7](https://github.com/chio-labs/sqlbuild/commit/bf2a2c7814fae9aa2e7a10b83964a81412e81db7))
* polish plan selectors and runtime artifacts ([f2f0633](https://github.com/chio-labs/sqlbuild/commit/f2f0633da597634a6a33863635adcc1a2f76345e))
* propagate UDF definition changes ([5e87a9c](https://github.com/chio-labs/sqlbuild/commit/5e87a9c08d105d47f44bf226f81497d7c3d77470))
* propagate UDF definition changes ([12e2125](https://github.com/chio-labs/sqlbuild/commit/12e2125296dff4cf009a1e3af86424f7e194b591))
* refine query change warning behavior ([6c2a193](https://github.com/chio-labs/sqlbuild/commit/6c2a19383ae04847fad1586cf6797d6eb4f5f736))
* refresh latest tracked partition ([9ff283e](https://github.com/chio-labs/sqlbuild/commit/9ff283e60faff82878098f690c4c7d46b883a630))
* reject unsupported dbt refs ([4717d3b](https://github.com/chio-labs/sqlbuild/commit/4717d3ba301af8079b08e04bf4b863a412b1789b))
* remove dead test helpers, deduplicate write_repo_files into shared fixture, and strengthen ast hash test ([e5daeb2](https://github.com/chio-labs/sqlbuild/commit/e5daeb245b0f1233270153cf1e0a035389940f87))
* resolve model-backed cursor inputs at runtime ([423f9ff](https://github.com/chio-labs/sqlbuild/commit/423f9ff442457e51095dbec98f1580b9c2f7cbb7))
* scope snowflake test markers ([9ee43c2](https://github.com/chio-labs/sqlbuild/commit/9ee43c2ff0b71b74df887337ff6853c3c64d3ce5))
* show incremental strategy annotation on full-refresh build output ([288d8c2](https://github.com/chio-labs/sqlbuild/commit/288d8c2788a1007fb64397cd1113f0c98b38f9f2))
* show model count in audit and test command headers ([f528515](https://github.com/chio-labs/sqlbuild/commit/f528515ba1fe0562e2ef0a662594fb2d68d4b927))
* show seed failures and default quotechar ([cabd72c](https://github.com/chio-labs/sqlbuild/commit/cabd72c6dc78320d1dfe8546633d9c1f55704bcd))
* stabilize SQL tests with Snowflake UDFs ([239fa16](https://github.com/chio-labs/sqlbuild/commit/239fa16786dc45737b15e637e824d2d74e0cbf87))
* tighten config validation ([6adc4c2](https://github.com/chio-labs/sqlbuild/commit/6adc4c23ade8cc1613701866badbb41e0c26ab6b))
* use BigQuery copy promotion ([a4ccff9](https://github.com/chio-labs/sqlbuild/commit/a4ccff94258dbd7503ecb1b4039045e74e3d8c50))
* use BigQuery copy promotion ([386deb4](https://github.com/chio-labs/sqlbuild/commit/386deb49ebbbf625f55847dac0ca63b48240ae3f))
* use BigQuery MERGE for delete insert ([a0d1283](https://github.com/chio-labs/sqlbuild/commit/a0d12838dfc8165279b83e4103939e4e648c23dd))
* use BigQuery MERGE for delete insert ([da62a51](https://github.com/chio-labs/sqlbuild/commit/da62a51af74dc93ab8c5679572b663b56039a94b))
* use dynamic column widths in build progress output for better terminal usage ([0c89ad0](https://github.com/chio-labs/sqlbuild/commit/0c89ad002a596d174c3125b66296f277e326dee0))
* validate cursor input names ([ec1a97a](https://github.com/chio-labs/sqlbuild/commit/ec1a97ab2d284eba42dbce91a6418970d9e31e48))
* validate declared inline source columns ([6969e03](https://github.com/chio-labs/sqlbuild/commit/6969e039d202bbab76fd6ed2267bf94f55bcb528))
* validate declared inline source columns ([da58065](https://github.com/chio-labs/sqlbuild/commit/da58065da0bbb6b6de5fa225772fca1f9978246e))
* validate hook sql at compile time ([6c370d1](https://github.com/chio-labs/sqlbuild/commit/6c370d1f51a5702295c5be7a3f7e59c877baee09))
* validate relation source metadata columns ([a0ed2c0](https://github.com/chio-labs/sqlbuild/commit/a0ed2c015421db8641143cb6761b70ab5c7941d2))
* wrap multi-statement DML in transactions for atomicity ([884bfbc](https://github.com/chio-labs/sqlbuild/commit/884bfbcfbf2cc7e639b1e8dc58cb960baefc567e))


### Documentation

* add project logo ([5e629c7](https://github.com/chio-labs/sqlbuild/commit/5e629c726fd637937800a0533f3959a04471e724))
* capture runtime SQL recording plan ([935e2d3](https://github.com/chio-labs/sqlbuild/commit/935e2d3cd557b9bd68fd0830d3c1fb5a802b8c36))
* enlarge README logo ([e6daafb](https://github.com/chio-labs/sqlbuild/commit/e6daafbc78cfb4306514760bd99cd0f50dfba27b))
* expand project README ([968b5f9](https://github.com/chio-labs/sqlbuild/commit/968b5f9bb905c9554af777d8a2312b67f5f00b2c))
* update feature overview ([607da90](https://github.com/chio-labs/sqlbuild/commit/607da901837f0dccbb5060f294b14d487da2408b))
* update README logo asset ([cce1d12](https://github.com/chio-labs/sqlbuild/commit/cce1d12df7289fcde8a7da42ae1f606ea206a0cd))
* update README positioning ([89fea65](https://github.com/chio-labs/sqlbuild/commit/89fea658c15dbd84450b554fed6bea163dfbbbfc))
* update README positioning ([832153e](https://github.com/chio-labs/sqlbuild/commit/832153e0bebbdbcade455c8d45a628a3f9bee923))

## Changelog

Release notes are managed by release-please.
