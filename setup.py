from setuptools import find_packages, setup


install_requires = (
    "neuromation>=20.4.6",
    "pytest",
    "pytest-dependency>=0.4.0",
    "pytest-timeout>=1.3.3",
    "pytest-aiohttp>=0.3.0",
)

setup(
    name="platform-e2e",
    version="0.0.1b1",
    url="https://github.com/neuromation/platform-e2e",
    packages=find_packages(),
    python_requires=">=3.7.0",
    install_requires=install_requires,
    entry_points={"pytest11": ["e2e = platform_e2e"]},
)
