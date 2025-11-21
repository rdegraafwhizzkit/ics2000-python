import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ics2000-python",
    version="1.0.4",
    author="Rutger de Graaf",
    author_email="",
    description="Trust ICS-2000 Python library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rdegraafwhizzkit/ics2000-python",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
    install_requires=[
        'numpy',
        'pycryptodome',
        'requests'
    ]
)
