<!-- generated-by: sqlbuild skills -->

# clean

> Remove compiled artifacts from the target directory.

Online: https://docs.sqlbuild.com/cli/clean

# sqb clean

Removes the `target/` directory containing compiled artifacts, runtime SQL recordings, and other build outputs.

## Usage

```bash
sqb --project-dir <path> clean
```

No flags. This command has no confirmation prompt since it only removes local build artifacts, not warehouse data.
