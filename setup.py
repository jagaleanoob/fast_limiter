import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="fastapi-rate-limiter",
    version="0.1.0",
    author="Jaime Galeano",
    author_email="ja.galeano.ba@gmail.com",
    description="A flexible rate limiting library for FastAPI applications",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/fastapi-rate-limiter",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.7",
    install_requires=[
        "fastapi>=0.68.0",
    ],
    extras_require={
        "redis": ["redis>=4.0.0"],
        "test": ["pytest>=7.0.0", "pytest-cov>=3.0.0", "httpx>=0.22.0"],
        "dev": ["black", "flake8", "isort", "mypy"],
    },
)
