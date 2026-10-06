# CHANGELOG

<!-- version list -->

## v1.0.0 (2026-10-06)

### Bug Fixes

- Do not use DICOM elements as scratch state (pydicom VR warnings)
  ([`c4be212`](https://github.com/eye2gene/process-dcm/commit/c4be21264ae4641dca416b2394eb4ed711a29baa))

### Documentation

- Describe the output contract and metadata schema history
  ([`9417560`](https://github.com/eye2gene/process-dcm/commit/9417560172c44ee0f13ac6175efd9ca10be9b289))

### Features

- Add opt-in options to mirror the input folder structure
  ([`8a95398`](https://github.com/eye2gene/process-dcm/commit/8a953986a36c4973c6d029ef8da8dfc0895ca467))

- Add SOP UIDs and circular B-scan locations to metadata (parser 1.6.0)
  ([`dbec56a`](https://github.com/eye2gene/process-dcm/commit/dbec56a02f8ccc60b4a69a25e816ab2c55b45485))

- Adopt e2g-pypkg template and drop Python 3.10
  ([`9a19f17`](https://github.com/eye2gene/process-dcm/commit/9a19f172929386f1863d4b2b5c165fa6c19b06f6))

- Improve modality detection and accept UTC offsets in DICOM datetimes
  ([`5663425`](https://github.com/eye2gene/process-dcm/commit/5663425a2958f165c6f9b9ccc1abd931adcc16a5))

- Record laterality and scan datetime per image (parser 1.7.0)
  ([`ea84e66`](https://github.com/eye2gene/process-dcm/commit/ea84e663984e682da47fcc745cfeee36f121ed82))

### Testing

- Accept the Linux Pillow 12 PNG hash in test_main_dummy
  ([`1808321`](https://github.com/eye2gene/process-dcm/commit/18083217eda6a7daa8e09483fe5f79fb0ac71198))

- Fix reserved.csv leaking into cwd and document the debug hook
  ([`a072769`](https://github.com/eye2gene/process-dcm/commit/a072769ff7b65250f139809772cf3248ea9e87d6))


## v0.10.0 (2025-07-09)

### Bug Fixes

- Update expected MD5 hash in `test_main_dummy` for consistency with latest changes
  ([`4ebe972`](https://github.com/eye2gene/process-dcm/commit/4ebe972490e2633f3b2161aad242b7b90e1a59db))

### Documentation

- Update README
  ([`7ace501`](https://github.com/eye2gene/process-dcm/commit/7ace501eae535a533f79281228253faf13275451))

### Features

- :sparkles: add `source_file` to metadata, increase parser_version to 1.5.3 DCM
  ([#4](https://github.com/eye2gene/process-dcm/pull/4),
  [`479676b`](https://github.com/eye2gene/process-dcm/commit/479676be554a1b06cae01548e18de942d91a6354))

### Testing

- Update MD5 assertion in `test_main_dummy` to allow multiple valid hashes
  ([`c747998`](https://github.com/eye2gene/process-dcm/commit/c7479986f80f9425fd0ea916054d6f6a9fb010f2))


## v0.9.0 (2025-04-09)

### Features

- Update input parameter to accept either a file or a folder
  ([`80ef80b`](https://github.com/eye2gene/process-dcm/commit/80ef80baa149066d62b8bdf3220c763d62e8292e))


## v0.8.0 (2025-04-08)

### Features

- Add example DICOM file for testing purposes
  ([`8b2f488`](https://github.com/eye2gene/process-dcm/commit/8b2f488b69144bc0ba143027e94a420975abc495))

- Enhance DICOM modality detection for OPTOS Optomap
  ([`48c413a`](https://github.com/eye2gene/process-dcm/commit/48c413a7004a12613db98890a03952465b68ef48))

- Update ipython dependency to version 8.35.0
  ([`972eb0e`](https://github.com/eye2gene/process-dcm/commit/972eb0ee004a0f0b9a43ccfa56f353d1cd680505))

- Update MD5 assertion in test_optomap for additional checksum validation
  ([`ac83df3`](https://github.com/eye2gene/process-dcm/commit/ac83df38f8f095f5ab4410bcd357fcbbff997765))


## v0.7.0 (2025-03-17)

### Chores

- Update cSpell.words and fix docstring formatting in utils.py
  ([`849a04f`](https://github.com/eye2gene/process-dcm/commit/849a04f1bbf062c0709d6337b2886d6b4e531894))

- Update cSpell.words in VSCode settings
  ([`c62c5e1`](https://github.com/eye2gene/process-dcm/commit/c62c5e1885f1f14dcada77ba787046775a0248ec))

### Documentation

- Update README with new usage instructions
  ([`39f6bb9`](https://github.com/eye2gene/process-dcm/commit/39f6bb9fe02648cc85571e244f35b8b1e99ad8e5))

### Features

- Add reset option to main function and enhance DCM file handling
  ([`9053298`](https://github.com/eye2gene/process-dcm/commit/90532988918d4ce9a2f2444c35e21a49c595f9f8))

- Enable parallel processing and enhance test coverage with new DICOM examples
  ([`7410fb4`](https://github.com/eye2gene/process-dcm/commit/7410fb4c3cf3acd4a71efef4f43d242870423b6c))

- Huge refactoring and add DICOMDIR support
  ([`fc0e937`](https://github.com/eye2gene/process-dcm/commit/fc0e9374f58e8ad368ff33324d87f977e628574c))

- Update README and main function to clarify '--tol' option usage and set default tolerance
  ([`ea8524e`](https://github.com/eye2gene/process-dcm/commit/ea8524e9401f0811cc48b2bead291a2435bedb97))

- Update test assertions to include additional MD5 checks for consistency
  ([`3c0d077`](https://github.com/eye2gene/process-dcm/commit/3c0d077762004d8618290ccfa85fd722e5f9e8a1))

### Refactoring

- Update process_dcm function to use Path objects and clean up tests
  ([`4960547`](https://github.com/eye2gene/process-dcm/commit/4960547c09ce0ae4831f2f7d8085ba70b9ccd709))


## v0.6.1 (2025-03-12)

### Chores

- Remove jupyterlab dependency from pyproject.toml
  ([`00ff626`](https://github.com/eye2gene/process-dcm/commit/00ff626cdebfea3f5ebc200ea4687b1f7030d223))

### Refactoring

- Add type hints to test functions in test_const.py
  ([`95357c2`](https://github.com/eye2gene/process-dcm/commit/95357c22136791fda98dfe323bd546c94d20396f))


## v0.6.0 (2025-03-12)

### Chores

- Add workflow_dispatch trigger to release workflow
  ([`c7afd87`](https://github.com/eye2gene/process-dcm/commit/c7afd87e5435c986df9d5ae3a292a7e4b024254a))

- Update GitHub Actions to use ubuntu-latest instead of ubuntu-20.04
  ([`cbf201c`](https://github.com/eye2gene/process-dcm/commit/cbf201c159563ffa482d39c6fe57f6e80c68c132))

- Update mypy configuration in settings and pyproject.toml
  ([`869ada9`](https://github.com/eye2gene/process-dcm/commit/869ada9ac408ef72715a1a836d1cf1006ac2adc3))

### Features

- Enhance DICOM processing by filtering out empty modalities and improving file type checks
  ([`f3b2418`](https://github.com/eye2gene/process-dcm/commit/f3b2418330de47e46342c3a2aa22b9162af7d692))


## v0.5.0 (2025-02-04)

### Features

- Add OPTOS_FA modality and corresponding test case
  ([`a1ea499`](https://github.com/eye2gene/process-dcm/commit/a1ea49946d9e21ff1b0beeaed10600b8105f4472))


## v0.4.9 (2025-02-04)

### Bug Fixes

- Add thread safety to folder deletion process
  ([`eac0d7d`](https://github.com/eye2gene/process-dcm/commit/eac0d7df9fc3e64099ef1126ae7c935c6efca955))

- Fix typings
  ([`759574c`](https://github.com/eye2gene/process-dcm/commit/759574cfdf4a7f8ba467340441c6c77c4f352c0b))

- Sort DICOM files when loading from input directory
  ([`b98f3a5`](https://github.com/eye2gene/process-dcm/commit/b98f3a576f1a67675b6a7b3bd2572e2deae3ca23))

- Update version provider from poetry to pep621 in pyproject.toml
  ([`01e3b63`](https://github.com/eye2gene/process-dcm/commit/01e3b63e6573c4bf16158f5abf866bab5f831348))

### Chores

- Update dependencies and improve project configuration
  ([`2a33382`](https://github.com/eye2gene/process-dcm/commit/2a333825542540a5538ec50d912320e14130c924))

bumped dependencies

### Testing

- Add tree function to display directory structure recursively for debug test
  ([`b1c688f`](https://github.com/eye2gene/process-dcm/commit/b1c688f56336196ab40f4dbc31418727e0be85e1))

- Debug test_main_dummy
  ([`0a916ec`](https://github.com/eye2gene/process-dcm/commit/0a916ec240dacd0b79274966eb3f3d8e6a0eaa0b))

- Debug test_main_dummy
  ([`85c3d6a`](https://github.com/eye2gene/process-dcm/commit/85c3d6a9a4fe88d2011f4977522dbddbe055bd94))

- Update delete_if_empty to support multi-threading in mixed structure test
  ([`2465dae`](https://github.com/eye2gene/process-dcm/commit/2465daeee5c205695bc02598889341567dec83bc))


## v0.4.8 (2024-11-28)

### Bug Fixes

- :bug: Fix bug about existing folder when using re-group option
  ([`e44f217`](https://github.com/eye2gene/process-dcm/commit/e44f217c59b48949358a5d8cf8fe7894fa27de30))

### Code Style

- :pencil2: Typos
  ([`2583530`](https://github.com/eye2gene/process-dcm/commit/2583530bd2fb14eaebf397fc7137835f7785aa93))


## v0.4.7 (2024-11-13)

### Bug Fixes

- Improve output details for unknown modalities
  ([`23ba602`](https://github.com/eye2gene/process-dcm/commit/23ba6022dddd67345212bda6824ec59a798dfb50))


## v0.4.6 (2024-11-13)

### Bug Fixes

- :bug: Avoid overwriting images in some scenarios
  ([`ad40e57`](https://github.com/eye2gene/process-dcm/commit/ad40e570999a10a53098466087be58f7237de6f3))


## v0.4.5 (2024-11-13)

### Bug Fixes

- :bug: Improve the way to handle AcquisitionDateTime
  ([`65afd80`](https://github.com/eye2gene/process-dcm/commit/65afd80f980bb5d67162dc88437c84b5f663e176))

Some typos fixed, set group_UNK if issues with AcquisitionDateTime and report, handle
  AcquisitionDateTime without ms


## v0.4.4 (2024-11-12)

### Bug Fixes

- :bug: Able to handle OPTOS PSEUDOCOLOUR_ULTRAWIDEFIELD modality
  ([`728cc86`](https://github.com/eye2gene/process-dcm/commit/728cc8638223d3172ed557bb1c4b2f2e81fb5af9))


## v0.4.3 (2024-11-12)

### Bug Fixes

- :bug: Added tolerance parameter for grouping AcquisitionDateTime
  ([`e0265c3`](https://github.com/eye2gene/process-dcm/commit/e0265c3334a92b51e2f4465cc9131eaa355a6670))


## v0.4.2 (2024-09-30)


## v0.4.1 (2024-09-30)

### Bug Fixes

- :bug: Fix output dir bug
  ([`dc19863`](https://github.com/eye2gene/process-dcm/commit/dc19863756d7f77b934da5a6be29e0854cb322e1))

- :bug: Fix wrong py_dcm_version in metadata.json
  ([`1ea9a2d`](https://github.com/eye2gene/process-dcm/commit/1ea9a2d09f7fd2d4489b832dd1f5859e1b07e252))

### Chores

- **deps**: Update to use pydicom 3.0.1
  ([`1eb3ce4`](https://github.com/eye2gene/process-dcm/commit/1eb3ce4679abbe371c29e2b0aba060581161c670))

### Continuous Integration

- :construction_worker: Run pytest on PRs
  ([`11f91fc`](https://github.com/eye2gene/process-dcm/commit/11f91fcd3411cb298ee76701b5542d728662da1a))

- :construction_worker: Some CI refinement
  ([`c9fda5d`](https://github.com/eye2gene/process-dcm/commit/c9fda5d2ca918768015ed92c704a8a46ccd48422))


## v0.4.0 (2024-09-16)

### Bug Fixes

- :bug: Fix issue with anonymised folder output
  ([`306e0fd`](https://github.com/eye2gene/process-dcm/commit/306e0fdab065043756c7af996acc03f2279e5f57))

### Documentation

- Update README
  ([`0036a6f`](https://github.com/eye2gene/process-dcm/commit/0036a6fe10924104aa68c329ac7be16f9ba828b3))

### Features

- :sparkles: Option to re-group DCM results by AcquisitionDateTime
  ([`0c4b282`](https://github.com/eye2gene/process-dcm/commit/0c4b2829b6297599ace956489c036b2017b38601))

### Testing

- :test_tube: Improve tests
  ([`d243813`](https://github.com/eye2gene/process-dcm/commit/d2438138efdb6174f1765949aff789668b892514))


## v0.3.0 (2024-09-11)

### Continuous Integration

- Fix CI to skip another long test
  ([`0ba40af`](https://github.com/eye2gene/process-dcm/commit/0ba40afe88d365def38f2c0863bd7704a1e2cddb))

### Features

- :sparkles: Make it compatible with python >=3.10
  ([`35578fc`](https://github.com/eye2gene/process-dcm/commit/35578fc50b292206eb219419a8af5cd343f882ed))


## v0.2.2 (2024-09-11)

### Bug Fixes

- :bug: Fix absolute path for output_dir issue
  ([`0bf2d86`](https://github.com/eye2gene/process-dcm/commit/0bf2d86f62d80f25f4224e591c63d897f238efd7))


## v0.2.1 (2024-09-09)

### Bug Fixes

- Fix the abort case and test
  ([`285ef76`](https://github.com/eye2gene/process-dcm/commit/285ef761ae24a10a39c47fc04bd29d3b40ad20c1))

- Update to pydicom 3.0 and fixed some typos
  ([`0cdfddb`](https://github.com/eye2gene/process-dcm/commit/0cdfddb2d7363cbb78ff5960b520cbf5380c9378))


## v0.2.0 (2024-09-05)

### Chores

- Added pypi badge
  ([`17c3bcd`](https://github.com/eye2gene/process-dcm/commit/17c3bcd9564c262e5e5ad2429831021a5780f105))

- Updated README
  ([`0cffce6`](https://github.com/eye2gene/process-dcm/commit/0cffce6d8afb712af062898d50865ee42a0ecd03))

- Updated README
  ([`00f56c1`](https://github.com/eye2gene/process-dcm/commit/00f56c1c5652489477251df6b1e7cf05f048faea))

### Continuous Integration

- :green_heart: fix CI logic when there's no version bump
  ([`345d960`](https://github.com/eye2gene/process-dcm/commit/345d9608645d98a0b8212dc16985083a1f60715e))

- :green_heart: Run CI only if critical files are changed
  ([`e251859`](https://github.com/eye2gene/process-dcm/commit/e2518597919e3236085ef0703500580b9a8956c8))

- :green_heart: Skip length tests
  ([`6e56e3c`](https://github.com/eye2gene/process-dcm/commit/6e56e3c6c38165985dbaa90dd3e3c34aff2596d1))

### Features

- :sparkles: Added anonymiser option by default
  ([`eea973f`](https://github.com/eye2gene/process-dcm/commit/eea973f74b25bfb69510499c6337ee50b0be6c6e))

### Testing

- Added a note to skip some tests in CI
  ([`33701e1`](https://github.com/eye2gene/process-dcm/commit/33701e1a0fe8dfd5e64e36e61d33505ebdbe640f))


## v0.1.1 (2024-09-04)

### Bug Fixes

- :bug: Assign the right group id for multi-groups cases in metadata.json
  ([`bc34be8`](https://github.com/eye2gene/process-dcm/commit/bc34be840e90841869d3fa7dca7e2efa68805eca))


## v0.1.0 (2024-07-31)

### Bug Fixes

- :bug: Attempt to fix GH action
  ([`5041a66`](https://github.com/eye2gene/process-dcm/commit/5041a66b5af643279216939569e0d0ab5800205c))

### Features

- :bookmark: Added GH action
  ([`2bc1d14`](https://github.com/eye2gene/process-dcm/commit/2bc1d1407a7ba072857519cced76f4607f55bef9))


## v0.0.2 (2024-07-31)

### Bug Fixes

- Fixed pyproject.toml for cz
  ([`b32dec6`](https://github.com/eye2gene/process-dcm/commit/b32dec6a9c8994db369dda5eb5f00e5651d3d342))


## v0.0.1 (2024-07-31)

### Chores

- Fixed repo url
  ([`2f4c1ea`](https://github.com/eye2gene/process-dcm/commit/2f4c1ea7055748acafa061dde79b844c1c90cdee))

### Documentation

- :memo: New README
  ([`aa788ae`](https://github.com/eye2gene/process-dcm/commit/aa788aeb09191731968f3231099db2c879359e89))

New functional release
