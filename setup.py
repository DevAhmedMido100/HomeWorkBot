from setuptools import setup, find_packages

setup(
    name="homework-bot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot==20.7",
        "flask==2.3.3", 
        "requests==2.31.0",
        "pillow==10.3.0",
        "python-dotenv==1.0.0"
    ],
)
