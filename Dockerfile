FROM inspection-backend
WORKDIR /app
COPY wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels/ flask dashscope
COPY app.py .
COPY templates/ templates/
EXPOSE 5000
CMD ["python3", "app.py"]
