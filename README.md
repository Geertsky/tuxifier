# Ansible Collection - geertsky.tuxifier

```
Role belongs to geertsky/tuxifier
Namespace - geertsky
Collection - tuxifier
Version - 1.0.0
Repository - http://github.com/geertsky/tuxifier
```

Description: Partition and install a server from the initramfs build with [dracut-incubator](https://github.com/geertsky/dracut-incubator)


For a quick-start please see the [tuxifier-playbook repository](https://github.com/Geertsky/tuxifier-playbook).

## Modules

| Module | Description |
|--------|-------------|
| `geertsky.tuxifier.generate_minimal_install_info` | Resolves the packages and package groups of the `minimalpackages` of a distribution, with their dependencies, against its repository. Returns `packages`, a list of dicts with the `name` and the `url` of every package. |
| `geertsky.tuxifier.rpm_install` | Imports the GPG keys that are missing in the rpm keyring of a root and installs the packages that are not installed in that root, with `rpm`. Can reimport the rpm database with the `rpmdb` of the installed system. Running it again changes nothing. |

See `ansible-doc geertsky.tuxifier.rpm_install` for the parameters and return values.
