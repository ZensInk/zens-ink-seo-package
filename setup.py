from setuptools import setup, find_packages

setup(
    name="zens-ink",
    version="1.4.6",
    description="Free SEO toolkit for indie builders — zero dependencies",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Jask",
    url="https://github.com/ZensInk/zens-ink-seo-package",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[],  # Zero dependencies — pure stdlib
    entry_points={
        "console_scripts": [
            "zens-ink=zens_ink.__main__:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP :: Site Management",
    ],
)
